# Flowsheet Toolbox

Web platform for Aspen HYSYS-based digital-twin workflows: simulation execution, surrogate modeling, calibration, and analysis.

## Purpose

Flowsheet Toolbox is designed to connect rigorous process simulation with data-driven model maintenance in one practical engineering workflow.

The main goal is to help users:

- run and manage HYSYS cases in a structured way,
- build surrogate models from simulation data,
- calibrate model parameters against plant or reference datasets,
- maintain surrogate accuracy over time with online learning,
- analyze, compare, and export results for engineering decisions.

In short, the platform reduces manual effort in model upkeep and supports faster, repeatable digital-twin operation.

## Main Parts of the Tool

1. Case Management
- Create and organize simulation cases.
- Configure input and output parameter mappings.
- Keep model metadata and files in one place.

2. Simulation
- Execute HYSYS simulations from the web UI.
- Store and review run results.
- Use batch simulation flows for larger datasets.

3. Surrogate Modeling
- Train machine learning surrogates from simulation data.
- Save/load trained models and scalers.
- Use surrogates for faster prediction-based workflows.

4. Calibration
- Single calibration and batch calibration workflows.
- Online learning calibration workflow for sequential datasets.
- Support for optimizer settings (currently PSO-based flow).

5. Analysis and Visualization
- Compare runs and inspect parameter-level behavior.
- Visualize row-wise calibration quality and metrics.
- Export results to Excel for reporting and post-processing.

## Future Opportunities

The platform can be extended with:

- Optimization cases for automated operating-point and decision-variable search.
- Explainability methods to improve model transparency and support engineering trust (for example feature-importance and local explanation workflows).

## Typical Workflow

1. Create a case and configure parameter mappings.
2. Run simulations or generate batch data.
3. Train a surrogate model.
4. Run calibration (single, batch, or online learning).
5. Review metrics/charts and export results.

## Installation

### Prerequisites

- Windows OS (required for HYSYS COM integration)
- Aspen HYSYS 10.0+
- Python 3.8+

### Setup

1. Clone the repository:
```bash
git clone https://github.com/bpalotai/Hysys-Simulation.git
```

2. Install dependencies:
```bash
install/install.bat
```

3. Start the application:
```bash
Start.bat
```

4. Open:
```text
http://localhost:5000
```

## Notes

- This tool was created from methods developed during PhD research, and the core system is continuously updated as those methods evolve and new results are produced.
- Because of this ongoing integration, some modules may temporarily be less tightly connected, and occasional bugs can occur.
- This software is intended for research and engineering use.
- It is not affiliated with or endorsed by Aspen Technology, Inc.

## How to Cite

If you use this toolbox in academic work, please cite:

```bibtex
@article{palotai2025online,
  title={Online learning supported surrogate-based flowsheet model maintenance},
  author={Palotai, Bal{\'a}zs and Kis, G{\'a}bor and Chov{\'a}n, Tibor and B{\'a}rk{\'a}nyi, {\'A}gnes},
  journal={Digital Chemical Engineering},
  pages={100287},
  year={2025},
  publisher={Elsevier},
  doi={10.1016/j.dche.2025.100287}
}
```

DOI: https://doi.org/10.1016/j.dche.2025.100287
