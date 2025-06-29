# Hysys-Simulation

**A web-based interface for Aspen HYSYS simulation management, surrogate modeling, and analysis.**

## 🔍 Overview

**Hysys-Simulation** provides process engineers with a powerful platform to:

- Manage and execute Aspen HYSYS simulations  
- Build and train surrogate (ML-based) models  
- Calibrate simulation parameters against real-world data  
- Conduct advanced analysis (sensitivity, Monte Carlo, contribution)  
- Visualize and compare simulation results through an intuitive web interface

This tool bridges the gap between complex process simulations and data-driven engineering insights.

---

## ✨ Features

- **Simulation Management**: Run and manage HYSYS simulations through a user-friendly UI  
- **Case Management**: Create, configure, and store simulation cases  
- **Surrogate Modeling**: Build machine learning models to approximate simulation outputs  
- **Calibration**: Tune HYSYS parameters automatically to match experimental data  
- **Advanced Analysis**:
  - Sensitivity analysis (parameter impact)
  - Monte Carlo simulations (uncertainty quantification)
  - Contribution analysis (parameter importance)
  - Comparative analysis (multiple simulations)
- **Visualization**: Interactive plots and tables for simulations and analyses

---

## ⚙️ Installation

### Prerequisites

- Windows OS (required for HYSYS integration)
- Aspen HYSYS (version 10.0 or later)
- Python 3.8+

### Steps

1. Clone this repository or download as ZIP:
   ```bash
   git clone https://github.com/bpalotai/Hysys-Simulation.git

   ```

2. Install the required Python packages:
   ```bash
    install/install.bat
    ```

3. Run the application:
   ```bash
   Start.bat

   ```
4. Open your browser and go to:
   ```bash
   http://localhost:5000

   ```

## 🧪 Usage Guide

### ➕ Creating a New Case

1. Go to **Cases**
2. Click **Create New Case**
3. Name and describe your case
4. Upload or specify your `.hsc` HYSYS file
5. Configure inputs/outputs via the settings interface

---

### ▶️ Running a Simulation

1. Select a case
2. Go to **Run Simulation**
3. Set parameters and click **Run**
4. View results on the **Results** page

---

### 🧠 Creating a Surrogate Model

1. Select a case
2. Navigate to **Surrogate Models**
3. Click **Create New Model**
4. Choose input/output variables and model type
5. Click **Train Model**

---

### 📊 Performing Analysis

1. Go to **Simulation Analysis**
2. Select a case and result set
3. Choose an analysis type:
   - **Sensitivity Analysis**
   - **Monte Carlo Simulation**
   - **Contribution Analysis**
4. Configure and run the analysis
5. View/export results

---

### 🛠️ Calibration

1. Go to **Calibration**
2. Select a case
3. Upload reference data or enter manually
4. Configure calibration settings
5. Run and evaluate results

## 🙏 Acknowledgments

- **Aspen Technology, Inc.** for Aspen HYSYS  
- Open-source contributors and Python ML/data libraries  

> ⚠️ *This project is not affiliated with or endorsed by Aspen Technology, Inc.*
