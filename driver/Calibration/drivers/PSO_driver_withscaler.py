import numpy as np
import math
import pandas as pd
from sklearn.metrics import mean_absolute_error,mean_squared_error, r2_score, mean_absolute_percentage_error
# fit scaler on your data
#X_norm = MinMaxScaler().fit(X)
class pso:
    '''
    Simple Particle Swarm Optimization
    Ref: https://machinelearningmastery.com/a-gentle-introduction-to-particle-swarm-optimization/
    '''
    def __init__(self, particles=dict(), opt_params=list(), y_true = dict(), y_scaler= None,iterations = 50, c1 = 0.1, c2 = 0.1, w = 0.8, stopping_treshold = 0.001, stopping_MSE = 0.1, debug=False, y_fitt = None, costnorm = None, fitparamlimit=None):
        self.particles = particles
        self.currentpoint = None
        self.opt_params = opt_params
        self.y_true = y_true
        self.y_fitt = y_fitt
        self.yscaler = y_scaler
        self.iterations = iterations
        self.c1 = c1
        self.c2 = c2
        self.w = w
        self.stopping_treshold = stopping_treshold
        self.stopping_MSE = stopping_MSE
        self.debug = debug
        self.gbest = None
        #self.costnorm = costnorm
        self.fitparamlimit = fitparamlimit

    def calc_cost(self, predicted_y_dict):
        # mean_squared_error
        if self.y_fitt == None:
            for k in self.y_true.keys():
                self.y_fitt[k]['Weight'] = 1
                self.y_fitt[k]['SDEV'] = 0

        ytrue_list = []
        y_pred_list = []
        weights = []
        abserrors = []
        for fp, w in self.y_fitt.items():
            weights.append(w)
            ytrue_list.append(self.y_true[fp])
            y_pred_list.append(predicted_y_dict[fp])

            # normálás előtt nézzünk egy absolut errort az elfogadási határhoz
            try:
                abs_deviation = abs(self.y_true[fp]-predicted_y_dict[fp])
            except:
                cost_sim_not_converge = 10000
                return cost_sim_not_converge
                #abs_deviation = 10000

            abserrors.append(abs_deviation)

        '''
        # Convert to numpy arrays
        ytrue_array = np.array(ytrue_list)
        ypred_array = np.array(y_pred_list)
        # L2 normalization
        ytrue_norm = ytrue_array / np.linalg.norm(ytrue_array)
        ypred_norm = ypred_array / np.linalg.norm(ypred_array)
        '''
        if self.yscaler:
            if hasattr(self.yscaler, 'feature_names_in_'):
                cols = list(self.yscaler.feature_names_in_)
                ytrue_dict = {k: self.y_true.get(k) for k in cols}
                ypred_dict = {k: predicted_y_dict.get(k) for k in cols}
                ytruenorm = self.yscaler.transform(pd.DataFrame([ytrue_dict], columns=cols))
                yprednorm = self.yscaler.transform(pd.DataFrame([ypred_dict], columns=cols))
            else:
                ytruenorm = self.yscaler.transform(np.array(ytrue_list).reshape(1, -1))
                yprednorm = self.yscaler.transform(np.array(y_pred_list).reshape(1, -1))

            ytrue_list = ytruenorm[0]
            y_pred_list = yprednorm[0]
        
        cost = 0
        for yt, yp, ww, abserr in zip(ytrue_list, y_pred_list, weights, abserrors):
            #Taguchi loss function
            if abserr > ww['SDEV']:
                if self.debug:
                    print(f"Absoluterror: {abserr}>{ww['SDEV']}")
                k = 1
            else:
                if self.debug:
                    print(f"Abs error in acceptance range: {abserr}<{ww['SDEV']}")
                k = 0.001

            cost += k * ((yt-yp)**2) * ww['Weight']


        #ytrue_list = list(self.y_true.values())
        #lentruelist = 1 # len(ytrue_list) # egy pontra illesztek
        #cost = np.sum((np.array(ytrue_list)-np.array(y_pred_list))**2) / lentruelist
        #cost = mean_squared_error(ytrue_list,y_pred_list)
        return cost

    def build_newinput(self, newopt = []):
        if len(self.opt_params) != len(newopt):
            raise Exception("Size of opt parameter list is not good.")

        new_inputlist = self.startingpoint.copy()
        for k, nv in zip(self.opt_params, newopt):
            new_inputlist[k] = nv

        self.currentpoint = new_inputlist
        
        return new_inputlist 

    # ezeket kell újra számolni global V, X, pbest, pbest_obj, gbest, gbest_obj
    def update_params(self, X, pbest, pbest_obj, velocity, gbest, driver):

        if self.fitparamlimit == None:
            self.fitparamlimit = {}
            for fk in self.opt_params:
                self.fitparamlimit[fk] = {'min':0, 'max':np.inf}

        # Update params, #TODO Ez majd később lehetne vector művelet
        r1, r2 = np.random.rand(2)
        newpoints = []
        newvelocities = []
        for valsc, valsbest, velo in zip(X, pbest, velocity):
            tempnewpoints = {}
            tempnewvelocities = {}
            for k, v in valsc.items():
                if k in self.opt_params:
                    V = self.w * velo[k] + self.c1*r1*(valsbest[k] - v) + self.c2*r2*(gbest[k]-v)

                    if v+V < self.fitparamlimit[k]['min']:
                        tempnewpoints[k] = self.fitparamlimit[k]['min']
                        tempnewvelocities[k] = self.fitparamlimit[k]['min'] - v
                        if self.debug:
                            print(f"Fitting ({k}) is less then limit {self.fitparamlimit[k]['min']} number: {v+V}, new value: {tempnewpoints[k]}")
                    elif v+V > self.fitparamlimit[k]['max']:
                        tempnewpoints[k] = self.fitparamlimit[k]['max']
                        tempnewvelocities[k] = self.fitparamlimit[k]['max'] - v
                        if self.debug:
                            print(f"Fitting ({k}) is higher then {self.fitparamlimit[k]['max']}: {v+V}, new value: {tempnewpoints[k]}")
                    else:
                        tempnewpoints[k] = v + V
                        tempnewvelocities[k] = V
                        #print(f"Fitting ({k}) is in the range Min:{self.fitparamlimit[k]['min']}-Max:{self.fitparamlimit[k]['max']}, {v+V}, new value: {tempnewpoints[k]}")
            
            newpoints.append(tempnewpoints)
            newvelocities.append(tempnewvelocities)     

        # új paraméterek összerakása
        newX = []
        costs = []
        predictions = []
        for xparams, newparams in zip(X, newpoints):
            tempgrid_newX = {}
            for pcol in xparams:
                if pcol in self.opt_params:
                    tempgrid_newX[pcol] = newparams[pcol]
                else:
                    tempgrid_newX[pcol] = xparams[pcol]
            newX.append(tempgrid_newX)
            # predict az új adatokkal
            ypreddict = driver.predict(tempgrid_newX)
            ypred = list(ypreddict.values())
            predictions.append(ypred)
            costs.append(self.calc_cost(ypreddict))

        # ahol jobb lett az eredmény ott rakjuk hozzá az új paramétereket
        pbest_new = []
        for prevc, newc, pbest_row, new_row in zip(pbest_obj, costs, pbest, newpoints):
            if prevc>=newc:
                tempgrid = {}
                for pcoln in pbest_row.keys():
                    if pcoln in self.opt_params:
                        tempgrid[pcoln] = new_row[pcoln]
                    else:
                        tempgrid[pcoln] = pbest_row[pcoln]
                pbest_new.append(tempgrid)
            else:
                pbest_new.append(pbest_row)

        # Update iterációs eredmények
        pbest_obj = costs.copy()

        minindex = costs.index(min(costs))
        gbest = pbest_new[minindex]
        gbest_obj = min(costs)

        return newX, pbest_new, pbest_obj, newvelocities, gbest, gbest_obj, predictions

    def run_pso(self, driver, costfunc = None):
        costs_values = []
        iovalues = []

        # Init X data, higy ne dict legyen hanem lista
        X = []
        for k, item in self.particles.items():
            X.append(item)

        # Init V data, a kezdeti paraméterek értéke * 0.1-el
        velocity = []
        for it in X:
            tempgridv = {}
            for pc in self.opt_params:
                tempgridv[pc] = it[pc]*0.1
            velocity.append(tempgridv)

        costs = []
        predictions_0 = []
        for id in X:
            ypreddict = driver.predict(id)
            ypred = list(ypreddict.values())
            predictions_0.append(ypred)
            costs.append(self.calc_cost(ypreddict))

        # Initialize data
        pbest = X.copy()
        pbest_obj = costs.copy()
        minindex = costs.index(min(costs))
        gbest = X[minindex]
        gbest_obj = min(costs)

        # Optimization
        prev_gbest = None

        # Rakjuk el az input-output paraméter kombinációkat későbbre
        iovaltemp = []
        for xitems, yitems in zip(pbest, predictions_0):
            tempinout = np.append(list(xitems.values()), yitems)
            iovaltemp.append(tempinout) 
        iovalues.append(iovaltemp)


        costs_values.append(costs)

        for i in range(self.iterations):


            X, pbest, pbest_obj, velocity, gbest, gbest_obj, predictions = self.update_params(X, pbest, pbest_obj, velocity, gbest, driver)
            
            costs_values.append(pbest_obj)

            iovaltemp = []
            for xitems, yitems in zip(X, predictions):
                tempinout = np.append(list(xitems.values()), yitems)
                iovaltemp.append(tempinout) 
            iovalues.append(iovaltemp)

            # legjobb pont kimentése
            self.gbest = gbest
            # leállási feltételek, hogy ne kelljen mindig végig iterálni
            if (prev_gbest and abs(prev_gbest-gbest_obj) < self.stopping_treshold):
                print(f"Treshold reached, best cost: {gbest_obj}, values: {gbest}")
                break

            if gbest_obj <= self.stopping_MSE:
                print(f"MSE Treshold reached, best cost: {gbest_obj}, values: {gbest}")
                break

            prev_gbest = gbest_obj

            if self.debug:
                print(f"#Iter: {i}, gbest_obj: {gbest_obj}")

            
        return costs_values, iovalues, gbest, gbest_obj
    
    def get_xydicforbest(self, costs_values, iovalues, gbest):
        bcost = costs_values[-1]
        bcostindes = bcost.index(min(bcost))

        bparam = iovalues[-1][bcostindes]
        xparam = list(self.particles[1].keys())
        totk = xparam + list(self.y_true.keys())
        iod = {}

        for k, v in zip(totk,bparam):
            iod[k]= v
                
        return iod
