# Replication Package — Empirical Study of Python Type-Annotation Modernization

This replication package supports the paper *"An Empirical Study of Python
Type-Annotation Modernization"* (ESEM 2025). It contains the complete toolchain
used to collect, process, and analyse type-annotation transformation events
extracted from the commit histories of 140 open-source Python projects.

The package is organised into three independent pipeline stages, each with its
own entry point (`Driver.py`):

```
data-collection/   ← clone repositories and run RefactoringMiner
data-processing/   ← convert raw JSON output into analysis-ready CSV
data-analysis/     ← reproduce all RQ results (tables and figures)
```

---

## Usage Scenarios

Choose the scenario that matches your goal:

| Scenario | Description | Time estimate |
|---|---|---|
| [Re-analysis of the existing dataset](#re-analysis-of-the-existing-dataset) | Download our frozen dataset from Zenodo and reproduce all RQ results directly | ~5 min |
| [Full replication](#full-replication) | Clone the exact project revisions we used and rerun the entire pipeline | several days |
| [New experiment](#new-experiment) | Run the pipeline on updated or different projects | varies |

---

## Requirements

### Python

```bash
python -m venv .
source bin/activate          # Windows: Scripts\activate
pip install pandas matplotlib numpy pandasql
```

### Java (data-collection only)

The mining tool (`jar/RM-fat.jar`) requires **Java 17 or later**.

```bash
java -version   # must report 17+
```

If your default `java` is older, point to a Java 17+ installation:

```bash
export JAVA_HOME=/path/to/java17
export PATH=$JAVA_HOME/bin:$PATH
```

### JAR (data-collection only)

`jar/RM-fat.jar` is not included in this repository (157 MB). Build it from
the [RefactoringMiner](https://github.com/tsantalis/RefactoringMiner) source:

```bash
git clone https://github.com/tsantalis/RefactoringMiner
cd RefactoringMiner
./gradlew shadowJar
cp build/libs/RM-fat.jar /path/to/this-repo/jar/
```

---

## Re-analysis of the Existing Dataset

**Goal:** reproduce all tables and figures from the paper using our frozen dataset,
without re-running data collection.

### 1 — Download the dataset from Zenodo

> **Dataset DOI:** `https://doi.org/10.5281/zenodo.XXXXXXX` *(to be published)*

Download and place the files as follows:

```
dataset/
├── all-results.zip    ← raw RefactoringMiner JSON outputs (optional, for data-processing)
└── final_ds.csv       ← curated dataset used in the paper (required for re-analysis)
```

### 2 — Run the analysis

```bash
cd data-analysis
python Driver.py
```

This runs all four analysis steps in sequence:

| Step | Script | Output |
|---|---|---|
| `rq1a` | `rq1_distribution.py` | `figures/boxplot_transformations.png`, `figures/transformations_over_time.png` |
| `rq1b` | `rq1_evolution.py` | `figures/transformations_over_time_prod_vs_test.png` |
| `rq2` | `rq2_commits.py` | `tables/refactoring_type_distribution.tex`, `tables/top_commits.tex` |
| `rq3` | `rq3_contributors.py` | `tables/contributor_concentration.tex`, `figures/contributor_pareto_global.pdf`, `figures/contributor_lorenz.pdf` |

To run a single step:

```bash
python Driver.py --steps rq1a
python Driver.py --steps rq2 rq3
```

---

## Full Replication

**Goal:** reproduce the study from scratch — clone the exact project revisions
we used, rerun RefactoringMiner, and regenerate `final_ds.csv`. This is
computationally intensive and may take **several days** depending on available
hardware.

### 1 — Clone the projects at the study revision

```bash
cd data-collection
python clone_projects.py /path/to/repos --replicate
```

The `--replicate` flag checks out the exact commit recorded in the
`study_revision` column of `projects.csv` after cloning. Omit it to clone
at `HEAD` instead (see [New Experiment](#new-experiment)).

### 2 — Run RefactoringMiner on all projects

```bash
python Driver.py /path/to/repos --output-dir /path/to/output
```

Progress is saved to `checkpoint.json` inside `--output-dir` after each
project, so an interrupted run can be safely resumed by re-running the same
command.

**Key options:**

| Option | Default | Description |
|---|---|---|
| `--output-dir` | `.` | Directory where `results/` and `checkpoint.json` are written |
| `--checkpoint` | `<output-dir>/checkpoint.json` | Custom checkpoint file location |

Results are written to `<output-dir>/results/<project>/<project>.json`.

### 3 — Convert JSON outputs to CSV

```bash
cd ../data-processing
python Driver.py
```

Or with explicit paths:

```bash
python json_to_csv.py \
  --input  /path/to/output/results \
  --output dataset/refactorings.csv
```

### 4 — Consolidate and classify type annotations

```bash
python consolidate_type_annotations.py \
  --input  dataset/refactorings.csv \
  --output dataset/final_ds.csv
```

Or run both steps together via the Driver:

```bash
python Driver.py
```

### 5 — Run the analysis

Follow [Re-analysis — Step 2](#2--run-the-analysis).

---

## New Experiment

**Goal:** run the pipeline on updated project snapshots (HEAD) or a different
set of projects.

### 1 — Edit `projects.csv`

`data-collection/projects.csv` contains the 140 projects used in the original
study. To use different projects, edit the `name` column (format: `owner/repo`).
The `study_revision` column is ignored when `--replicate` is not passed.

### 2 — Clone at HEAD

```bash
cd data-collection
python clone_projects.py /path/to/repos
```

### 3 — Collect, process, and analyse

Follow steps 2–5 of [Full Replication](#full-replication).

---

## Repository Layout

```
data-collection/
├── Driver.py                      ← orchestrates RefactoringMiner across all repos
├── run_refactoringminer.py        ← JAR wrapper for a single repository
├── clone_projects.py              ← clone repos from projects.csv
├── projects.csv                   ← 140 projects with study_revision
└── snapshot_revisions.py          ← utility to record HEAD revisions of cloned repos

data-processing/
├── Driver.py                      ← json_to_csv → consolidate_type_annotations
├── json_to_csv.py                 ← merge JSON result files → refactorings.csv
└── consolidate_type_annotations.py ← cross-commit classification → final_ds.csv

data-analysis/
├── Driver.py                      ← rq1a → rq1b → rq2 → rq3
├── rq1_distribution.py            ← RQ1: per-repo transformation distribution
├── rq1_evolution.py               ← RQ1: temporal evolution
├── rq2_commits.py                 ← RQ2: commit-level analysis
└── rq3_contributors.py            ← RQ3: contributor concentration

jar/
└── RM-fat.jar                     ← RefactoringMiner executable (not in repo — build locally)

dataset/                           ← data files (not in repo — download from Zenodo)
├── final_ds.csv                   ← curated dataset (re-analysis starting point)
└── all-results.zip                ← raw JSON outputs (full replication starting point)

figures/                           ← generated plots (committed for reference)
tables/                            ← generated LaTeX tables and CSVs (committed for reference)
```

---

## Dataset Description

`dataset/final_ds.csv` contains **one row per detected transformation**.

| Column | Description |
|---|---|
| `project_name` | Short project identifier |
| `repository` | GitHub clone URL |
| `commit_id` | Full SHA of the commit |
| `commit_url` | GitHub URL for the commit |
| `author_name` / `author_email` | Commit author |
| `commit_time` | ISO-8601 timestamp (UTC) |
| `refactoring_type` | E.g. `Add Variable Type Annotation` |
| `description` | Human-readable description of the change |
| `left_file_path` / `right_file_path` | File path before / after the change |
| `left_start_line` / `left_end_line` | Line range before the change |
| `right_start_line` / `right_end_line` | Line range after the change |
| `is_test_code` | `production` or `test` |

---

## Citation

> *Citation details will be added upon publication.*
