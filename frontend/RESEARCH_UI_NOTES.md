# AI Compass frontend — research-strengthening changes

## What changed

1. **Research validity checks on Evaluation**
   - Makes the current sample size and limitations visible.
   - States that candidate-pool parity is not guaranteed because the current baseline endpoint applies its own default filtering and does not inherit the original route's hard constraints.
   - Describes quality as heuristic and explains why the current comparison is not a statistical benchmark.

2. **AI Compass route context**
   - Displays the current route's selected/final model, heuristic quality score, estimated cost, total latency, acceptance status, and evaluator method separately from baseline calls.
   - Avoids presenting the route and baselines as perfectly paired measurements when they were executed in separate calls.

3. **Research exports**
   - JSON and CSV exports contain the query, profile, strategy, selected/final models, score, cost estimate, latency fields, reliability definition, escalation, usage, model candidates and caveats.
   - Generated response bodies are not exported.
   - Exported records distinguish AI Compass total latency from baseline provider-response latency, and distinguish the AI Compass reliability prior from the baseline blended reliability proxy.

4. **Honest terminology in Explanation and Evaluation**
   - Renames “Actual cost” to “Cost estimate”.
   - Labels the current alignment metric as a task/capability-fit proxy rather than validated personal-preference alignment.
   - Labels reliability values as proxies where appropriate.

5. **Small TypeScript build fixes**
   - Explicitly narrows discriminated `PatchResult` unions.
   - Provides the `StatusFilter` generic to the model-pool segmented control.

## What this does not claim

- It does not make the heuristic response evaluator a validated quality benchmark.
- It does not guarantee candidate-pool parity or identical hard constraints for baseline strategies.
- It does not add repeated trials, confidence intervals, or significance tests.
- It does not prove that AI Compass outperforms any baseline.
- It does not replace the need for a controlled experiment on a fixed query dataset.

## Validation

TypeScript compilation (`node node_modules/typescript/bin/tsc -b`) passed in the working environment.

The Vite production build could not be completed here because the uploaded `node_modules` directory contains macOS dependencies and lacks the Linux Rolldown native binding. This is an environment/dependency issue; reinstall dependencies on your development Mac before running `npm run build`.

## Recommended next backend changes

For valid research comparisons, update the backend evaluation endpoint to accept and apply the same candidate constraints as the original route, return the candidate IDs used for each strategy, and log a stable run ID, evaluator version, per-query metrics, actual token usage, and cost estimates. Then add a dataset-based evaluation runner with repeated trials and ablation configurations.
