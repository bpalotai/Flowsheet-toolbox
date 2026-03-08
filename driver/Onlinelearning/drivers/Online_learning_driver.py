from sklearn.base import clone
import pandas as pd
import numpy as np
from sklearn.neural_network import MLPRegressor
import copy
import time
from datetime import datetime
from sklearn.model_selection import train_test_split
import sys
import os

import joblib

class OnlineLearning:
    def __init__(self, surrogate_model, original_data, y_fitt = None, batch_size=1, 
                 replay_ratio=0.1, retrain_scaler=False, logger=None, retrain_type='incremental', error_batch_size=5):
        """
        Simplified online learning for surrogate model retraining
        
        Parameters:
            surrogate_model: surrogate_driver object
            original_data: DataFrame with original training data
            weights: Dictionary with parameter weights for calibration cost (e.g., {'param1': 1.0, 'param2': 2.0})
            batch_size: Number of outlier points to collect before retraining
            replay_ratio: Proportion of original data to include in each update
            retrain_scaler: Whether to retrain the scaler during online learning
            retrain_type: 'incremental' or 'cumulative' or 'hybrid' retraining
        """
        self.surrogate = surrogate_model
        self.original_data = original_data
        self.batch_size = batch_size
        self.replay_ratio = replay_ratio
        self.retrain_scaler = retrain_scaler
        self.retrain_type = retrain_type # Currently not used, only incremental implemented
        

        self.y_fitt = y_fitt if y_fitt is not None else {col: {'Weight': 1.0, 'SDEV': 0.0} for col in surrogate_model.y_cols}

        # Initialize tracking variables
        self.iteration_count = 0
        self.metrics_history = []
        self.learner_batch = []
        self.all_new_data = []
        self.error_batch = []
        self.error_batch_size = error_batch_size
        
        # Create experience replay buffer from original data
        self.replay_buffer = {
            'X': self.surrogate.scaler.x_scaler.transform(original_data[surrogate_model.x_cols]),
            'y': self.surrogate.scaler.y_scaler.transform(original_data[surrogate_model.y_cols])
        }
        
        # Store previous model for local improvement calculation
        self.base_model = copy.deepcopy(surrogate_model)
        self.previous_model = copy.deepcopy(surrogate_model)
        self.last_replay_indices = None

        if logger is None:
            import logging
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        else:
            self.logger = logger

    # TODO: It is dubplicated from PSO optimizer class, later it should be generalized
    @staticmethod
    def calc_cost(y_true_dict, y_pred_dict, y_fitt, y_scaler=None, debug=False):
        """
        General Taguchi-style cost function.
        
        Parameters
        ----------
        y_true_dict : dict
            True values, {feature_point: value}
        y_pred_dict : dict
            Predicted values, {feature_point: value}
        y_fitt : dict
            Dictionary with 'Weight' and 'SDEV' for each feature_point
        y_scaler : sklearn Scaler, optional
            If provided, normalize y_true and y_pred before cost calculation
        debug : bool
            If True, print debug info
        """
        # Initialize weights/SDEV if missing
        for k in y_true_dict.keys():
            if k not in y_fitt:
                y_fitt[k] = {'Weight': 1, 'SDEV': 0}

        ytrue_list = []
        y_pred_list = []
        weights = []
        abserrors = []

        # Build lists
        for fp, w in y_fitt.items():
            weights.append(w)
            yt = y_true_dict[fp]
            yp = y_pred_dict[fp]
            ytrue_list.append(yt)
            y_pred_list.append(yp)

            try:
                abs_deviation = abs(yt - yp)
            except Exception:
                return 1e4  # Simulation did not converge

            abserrors.append(abs_deviation)

        # Apply scaling if needed
        if y_scaler is not None:
            if hasattr(y_scaler, 'feature_names_in_'):
                cols = list(y_scaler.feature_names_in_)
                ytrue_df = pd.DataFrame([{k: y_true_dict.get(k) for k in cols}], columns=cols)
                ypred_df = pd.DataFrame([{k: y_pred_dict.get(k) for k in cols}], columns=cols)
                ytrue_list = y_scaler.transform(ytrue_df)[0]
                y_pred_list = y_scaler.transform(ypred_df)[0]
            else:
                ytrue_list = y_scaler.transform(np.array(ytrue_list).reshape(1, -1))[0]
                y_pred_list = y_scaler.transform(np.array(y_pred_list).reshape(1, -1))[0]

        # Taguchi loss function
        cost = 0
        for yt, yp, ww, abserr in zip(ytrue_list, y_pred_list, weights, abserrors):
            if abserr > ww['SDEV']:
                if debug:
                    print(f"Absolute error: {abserr} > {ww['SDEV']}")
                k = 1
            else:
                if debug:
                    print(f"Abs error in acceptance range: {abserr} < {ww['SDEV']}")
                k = 0.001

            cost += k * ((yt - yp) ** 2) * ww['Weight']

        return cost
    
    def add_data_point(self, x_input, y_true):
        """
        Add new data point and retrain if outlier batch is full
        
        Parameters:
            x_input: Input features (dict or DataFrame)
            y_true: True output values (dict or DataFrame)
        """
        # Convert to DataFrame if needed
        if isinstance(x_input, dict):
            x_df = pd.DataFrame([x_input])
        else:
            x_df = x_input
            
        if isinstance(y_true, dict):
            y_df = pd.DataFrame([y_true])
        else:
            y_df = y_true
        
        # Store all new data
        self.all_new_data.append({'X': x_df, 'y': y_df})
        
        # Add to batch
        self.learner_batch.append({'X': x_df, 'y': y_df})

    def add_data_point_to_error(self, x_input, y_true):
        """
        Add new data point and retrain if outlier batch is full
        
        Parameters:
            x_input: Input features (dict or DataFrame)
            y_true: True output values (dict or DataFrame)
        """
        # Convert to DataFrame if needed
        if isinstance(x_input, dict):
            x_df = pd.DataFrame([x_input])
        else:
            x_df = x_input
            
        if isinstance(y_true, dict):
            y_df = pd.DataFrame([y_true])
        else:
            y_df = y_true
        
        # Store all error data
        self.error_batch.append({'X': x_df, 'y': y_df})

    def init_retraining(self):        
        # Retrain if batch is full
        if len(self.learner_batch) >= self.batch_size:
            self.retrain_model()
            # TODO hybrid batch collections
            self.learner_batch = []  # Clear batch after retraining
            self.logger.info(f"Batch of {len(self.learner_batch)} points collected. Retraining model.")

    def _retrain_incremental(self):
        start_time = time.time()
        
        # Store previous model for local improvement calculation
        self.previous_model = copy.deepcopy(self.surrogate)
        
        # Prepare training data
        # Get replay data
        # replay based on the lenght of the original data and the new data
        #n_replay = int(len(self.learner_batch) * self.replay_ratio)
        # Alternatively, replay based on the fixed replay ratio
        n_replay = int(len(self.replay_buffer['X']) * self.replay_ratio)
        if n_replay > 0:
            replay_indices = np.random.choice(len(self.replay_buffer['X']), n_replay, replace=False)

            self.last_replay_indices = replay_indices
            #print(f"Selected replay indices: {replay_indices}")
            X_replay = self.replay_buffer['X'][replay_indices]
            y_replay = self.replay_buffer['y'][replay_indices]
        else:
            X_replay = np.array([]).reshape(0, len(self.surrogate.x_cols))
            y_replay = np.array([]).reshape(0, len(self.surrogate.y_cols))
        
        # Combine outlier batch data
        if self.learner_batch:
            X_newbatch = []
            y_newbatch = []
            self.logger.debug(f"Processing learner batch with {self.learner_batch} new data points for retraining.")
            for data_point in self.learner_batch:
                X_scaled = self.surrogate.scaler.x_scaler.transform(data_point['X'])
                y_scaled = self.surrogate.scaler.y_scaler.transform(data_point['y'])
                X_newbatch.append(X_scaled)
                y_newbatch.append(y_scaled)
            
            X_newbatch = np.vstack(X_newbatch)
            y_newbatch = np.vstack(y_newbatch)
            
            # Combine replay and outlier data
            X_train = np.vstack([X_replay, X_newbatch])
            y_train = np.vstack([y_replay, y_newbatch])
        else:
            X_train = X_replay
            y_train = y_replay
        
        # Retrain scaler if requested
        if self.retrain_scaler and self.all_new_data:
            self._retrain_scaler()
        
        # Create new model with same architecture If totaly new model is generated
        #model_params = self.surrogate.model.get_params()
        #new_model = MLPRegressor(**model_params)
        # Perform partial fit for the MLPRegressor
        model = self.surrogate.model
        if hasattr(model, 'warm_start'):
            model.warm_start = True
        # Turn off parameters that are incompatible or undesired for partial_fit.
        #if hasattr(model, 'early_stopping'):
        #    model.early_stopping = False
        #if hasattr(model, 'n_iter_no_change'):
        #    model.n_iter_no_change = 0
        #if hasattr(model, 'best_loss_') and model.best_loss_ is None:
        #    model.best_loss_ = np.inf
        #if hasattr(model, '_no_improvement_count'):
        #    model._no_improvement_count = 0
        #if hasattr(model, 'loss_curve_') and model.loss_curve_ is None:
        #    model.loss_curve_ = []
        #if hasattr(model, 'alpha'):
        #    model.alpha = 0.0
    
        # Set max_iter to a smaller value for partial_fit
        #original_max_iter = self.surrogate.model.max_iter
        model.max_iter = 50
        
        #self.model.partial_fit(X_batch, y_batch)
        
        # Restore original max_iter
        #self.model.max_iter = original_max_iter
        #new_model.warm_start = True
        #new_model.max_iter = 50  # Fewer iterations per update

        # Fit the model
        if len(X_train) > 0:
            self.logger.info(f"Retraining model with {len(X_train)} samples (replay + new)")
            #print(f"Retraining with X: {X_train} and y: {y_train}")
            #K=1
            #for _ in range(K):   # e.g. K=3..10
            model.partial_fit(X_train, y_train)
            
            # Update surrogate model
            version_name = f"online_v{self.iteration_count}"
            self.surrogate.add_model_version(model, version_name)
            try:
                self.surrogate.set_current_version(version_name)
            finally:
                self.logger.info(f"Self.model updated to {version_name}")
                #print(f"Self.model updated to {version_name}")
            
            training_time = time.time() - start_time
            
            # Calculate metrics
            #metrics = self._calculate_iteration_metrics(training_time)
            #self.metrics_history.append(metrics)
            
            self.iteration_count += 1
            
            self.logger.debug(f"Retrained model version: {version_name}")
            self.logger.debug(f"Model retrained (iteration {self.iteration_count})")
            self.logger.debug(f"Training time: {training_time:.3f}s")
            #self.logger.debug(f"Global accuracy: {metrics['global_accuracy_retention']:.6f}")
            #if metrics['local_improvement'] is not None:
            #    self.logger.debug(f"Local improvement: {metrics['local_improvement']:.3f}")

    def _retrain_cumulative(self):
        start_time = time.time()
        
        # Store previous model for local improvement calculation
        self.previous_model = copy.deepcopy(self.surrogate)

        X_replay =self.replay_buffer['X']
        y_replay = self.replay_buffer['y']
        # Combine outlier batch data
        if self.all_new_data:
            X_newbatch = []
            y_newbatch = []
            for data_point in self.all_new_data:
                X_scaled = self.surrogate.scaler.x_scaler.transform(data_point['X'])
                y_scaled = self.surrogate.scaler.y_scaler.transform(data_point['y'])
                X_newbatch.append(X_scaled)
                y_newbatch.append(y_scaled)
            
            X_newbatch = np.vstack(X_newbatch)
            y_newbatch = np.vstack(y_newbatch)
            
            # Combine replay and outlier data
            X_train = np.vstack([X_replay, X_newbatch])
            y_train = np.vstack([y_replay, y_newbatch])
        else:
            X_train = X_replay
            y_train = y_replay
        
        # Retrain scaler if requested
        if self.retrain_scaler and self.all_new_data:
            self._retrain_scaler()

        X_train_c, X_test_c, y_train_c, y_test_c = train_test_split(
            X_train, y_train, test_size=0.30, random_state=42)
        
        # ---- Build a fresh model FROM SCRATCH ----
        base_model = self.surrogate.model
        model = clone(base_model)  # same hyperparams, fresh weights/state

        # Ensure scratch behavior
        if hasattr(model, "warm_start"):
            model.warm_start = False

        # Optional reproducibility
        if hasattr(model, "random_state") and getattr(model, "random_state", None) is None:
            model.random_state = 42

        # Training knobs (only if present)
        if hasattr(model, "early_stopping"):
            model.early_stopping = True
        if hasattr(model, "n_iter_no_change"):
            model.n_iter_no_change = 30
        if hasattr(model, "alpha"):
            model.alpha = 1e-4
        if hasattr(model, "max_iter"):
            model.max_iter = 500

        # Fit the model
        if len(X_train_c) > 0:
            self.logger.info(f"Full-Retraining model with {len(X_train_c)} samples (replay + new)")
            #print(f"Retraining with X: {X_train_c} and y: {y_train_c}")
            model.fit(X_train_c, y_train_c)
            
            # Update surrogate model
            version_name = f"online_v{self.iteration_count}"
            self.surrogate.add_model_version(model, version_name)
            try:
                self.surrogate.set_current_version(version_name)
            finally:
                self.logger.info(f"Self.model updated to {version_name}")
                #print(f"Self.model updated to {version_name}")
            
            training_time = time.time() - start_time
            
            # Calculate metrics
            #metrics = self._calculate_iteration_metrics(training_time)
            #self.metrics_history.append(metrics)
            
            self.iteration_count += 1
            
            self.logger.debug(f"Retrained model version: {version_name}")
            self.logger.debug(f"Model retrained (iteration {self.iteration_count})")
            self.logger.debug(f"Training time: {training_time:.3f}s")

    def _retrain_hybrid(self):
        pass

    def retrain_model(self):
        """
        Retrain the model using outlier batch + experience replay
        """
        self.logger.info(f"Starting retraining using {self.retrain_type} strategy.")
        if self.retrain_type == 'incremental':
            self._retrain_incremental()
        elif self.retrain_type == 'cumulative':
            self._retrain_cumulative()
        elif self.retrain_type == 'hybrid':
            self._retrain_hybrid()
        else:
            # raise error not implemented
            raise Exception(f'Not proper retrain type set {self.retrain_type}, it can incremental or cumulative or hybrid!')

    
    def _retrain_scaler(self):
        """
        Retrain scaler with all available data
        """
        # Combine original and new data
        all_x_data = [self.original_data[self.surrogate.x_cols]]
        all_y_data = [self.original_data[self.surrogate.y_cols]]
        
        for data_point in self.all_new_data:
            all_x_data.append(data_point['X'])
            all_y_data.append(data_point['y'])
        
        combined_x = pd.concat(all_x_data, ignore_index=True)
        combined_y = pd.concat(all_y_data, ignore_index=True)
        
        # Refit scaler
        self.surrogate.scaler.fit(combined_x, combined_y)
        
        # Update replay buffer
        self.replay_buffer = {
            'X': self.surrogate.scaler.x_scaler.transform(self.original_data[self.surrogate.x_cols]),
            'y': self.surrogate.scaler.y_scaler.transform(self.original_data[self.surrogate.y_cols])
        }
    
    # TODO: it is not fully valid, as usually the x_next is not available for the calibrated parameters, it is available after sucessfull calibration. Here I used the test data where I have this information for validation purposes. 
    def calculate_local_improvement_for_next_point(self, x_next, y_true_next):
        """
        Calculate local improvement when next operational point arrives
        """
        self.logger.debug(f"Type of x_next is {type(x_next)} and y_true_next {type(y_true_next)}, x_next: {x_next}, y_true_next: {y_true_next}")

        # Switch to previous version
        #self.logger.debug(f"Previous model version: {self.previous_model}")
        pred_previous = self.previous_model.predict(x_next)
        self.logger.debug(f"Run prediction with prev model version: {self.previous_model.current_version}, result {pred_previous}")
        
        # Switch back to current model
        pred_current = self.surrogate.predict(x_next)
        self.logger.debug(f"Run prediction with current model version: {self.surrogate.current_version}, result {pred_current}")
        # Calculate calibration costs
        #:
        cost_current = self.calc_cost(y_true_next, pred_current, self.y_fitt, y_scaler=self.surrogate.scaler.y_scaler, debug=False)
        cost_previous = self.calc_cost(y_true_next, pred_previous, self.y_fitt, y_scaler=self.surrogate.scaler.y_scaler, debug=False)
        
        # Calculate improvement ratio
        if cost_current == 0:
            improvement = float('inf') if cost_previous > 0 else 1.0
        else:
            improvement = cost_previous / cost_current

        # TODO: Gives 1 always, should be fixed later
        
        return improvement
    
    def calculate_global_accuracy_retention(self):
        """
        Calculate global accuracy retention metric γ_F^(t) based on original offline dataset.
        Uses the same cost function as local improvement for consistency.

        γ_F^(t) = F(s^(0), D_offline) / F(s^(t), D_offline)

        Returns
        -------
        float
            Ratio indicating global accuracy retention.
            ~1.0 => retention, <1.0 => forgetting, >1.0 => improvement.
        """
        if self.original_data is None or len(self.original_data) == 0:
            raise ValueError("Original offline dataset (self.original_data) is not available.")

        # Store current model version name
        current_version_name = self.surrogate.current_version

        # --- 1. Evaluate baseline model s^(0) ---
        if "base" not in self.surrogate.model_versions:
            raise ValueError("Baseline model version 'base' not found.")

        baseline_costs = []
        for _, row in self.original_data.iterrows():
            x_input = row[self.surrogate.x_cols].to_dict()
            y_true = row[self.surrogate.y_cols].to_dict()
            y_pred = self.base_model.predict(x_input)
            cost = self.calc_cost(y_true, y_pred, y_fitt = self.y_fitt, y_scaler=self.surrogate.scaler.y_scaler, debug=False)
            baseline_costs.append(cost)
        baseline_cost = np.mean(baseline_costs)
        self.logger.debug(f"Run prediction on original data with base model {self.base_model.current_version} version, cost {baseline_cost}")

        # --- 2. Evaluate current model s^(t) ---
        current_costs = []
        for _, row in self.original_data.iterrows():
            x_input = row[self.surrogate.x_cols].to_dict()
            y_true = row[self.surrogate.y_cols].to_dict()
            y_pred = self.surrogate.predict(x_input)
            cost = self.calc_cost(y_true, y_pred, y_fitt = self.y_fitt, y_scaler=self.surrogate.scaler.y_scaler, debug=False)
            current_costs.append(cost)
        current_cost = np.mean(current_costs)
        self.logger.debug(f"Run prediction on original data with {self.surrogate.current_version} version, cost {current_cost}")

        # --- 3. Calculate ratio γ_F^(t) ---
        if current_cost == 0:
            gamma_F = float('inf') if baseline_cost > 0 else 1.0
        else:
            gamma_F = baseline_cost / current_cost

        # TODO: Gives 1 always, should be fixed later

        return gamma_F

    def save_model(self, path='Models/', filename=None, version='current'):
        """Save model with metadata and version handling"""
        # Create directory if it doesn't exist
        os.makedirs(path, exist_ok=True)
        
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"surrogate_model_{timestamp}.joblib"
        
        # Select model version to save
        if version == 'current':
            model_to_save = self.surrogate.model
            version_name = self.surrogate.current_version
        elif version in self.surrogate.model_versions:
            model_to_save = self.surrogate.model_versions[version]
            version_name = version
        else:
            print(f"Version '{version}' not found. Saving current model.")
            model_to_save = self.surrogate.model
            version_name = self.surrogate.current_version
        
        # Save model and metadata together
        model_data = {
            'model': model_to_save,
            'x_cols': self.surrogate.x_cols,
            'y_cols': self.surrogate.y_cols,
            'scaler': self.surrogate.scaler,
            'model_versions': self.surrogate.model_versions,
            'current_version': version_name,
            'saved_version': version_name,
            'timestamp': datetime.now(),
            'class_type': 'surrogate_driver'
        }
        
        full_path = os.path.join(path, filename)
        joblib.dump(model_data, full_path)
        print(f"Model (version: {version_name}) saved to {full_path}")
        return full_path
