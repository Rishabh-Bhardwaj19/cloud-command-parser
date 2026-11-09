# Negative model quality-gate demonstration

- Workflow: Negative Model Quality Gate Demonstration
- Run: https://github.com/Rishabh-Bhardwaj19/cloud-command-parser/actions/runs/42552381986
- Failed job: https://github.com/Rishabh-Bhardwaj19/cloud-command-parser/actions/runs/42552381986/job/128950598887
- Commit: 6d93da7
- Expected outcome: the untrained Pythia-70M baseline must fail the 95% JSON-validity quality gate.
- Measured score from `negative_gate_report.json`: JSON validity 0.0%; intent accuracy 0.0%; date accuracy 0.0%; time accuracy 0.0%; place accuracy 0.0%; full-frame accuracy 0.0%.
- Evaluation set: 100 validation examples; missing predictions: 0.
- Interpretation: prediction generation completed, scoring ran, and the workflow failed specifically because 0.0% JSON validity is below the 95.0% minimum. The evidence artifact was uploaded successfully by the workflow.
