# Frozen model execution environments

Two environment roles are intentionally isolated:

- `classical`: controller, preprocessing, calibration and classical estimators;
- `qnn_mlp`: PyTorch MLP and analytic PennyLane QNN workers.

Create a fresh virtual environment with the exact interpreter from
`.python-version`, then install `requirements.lock` with
`python -m pip install --require-hashes -r requirements.lock`.  The controller
sets all frozen thread variables to `1` before auditing or starting a worker.

IBM Quantum and AWS Braket plugins are intentionally absent.  Their reserved
adapter boundary is declared in
`configs/production_experiment_runner_v1_0_0.yaml`; activation would require a
new explicit preregistration version.
