import pandas as pd
from river.drift import ADWIN
from collections import deque
from autogluon.tabular import TabularPredictor
import numpy as np
import time
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
import matplotlib.pyplot as plt


def load_csv(path):
    try:
        df = pd.read_csv(path)
        print("CSV loaded successfully!")
        return df
    except FileNotFoundError:
        print(f"Error: The file '{path}' was not found.")
    except pd.errors.EmptyDataError:
        print(f"Error: The file '{path}' is empty.")
    except pd.errors.ParserError:
        print(f"Error: The file '{path}' contains malformed data and could not be parsed.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def predict_autogluon(predictor, row, feature_cols):
    """Use an AutoGluon TabularPredictor to get the predicted class for a single row."""
    X = pd.DataFrame([row[feature_cols]])
    return predictor.predict(X).iloc[0]


def monitor_drift_and_retrain(df, predictor, feature_cols, target_col, window_size=100):
    """Monitor for concept drift using ADWIN and retrain an AutoGluon model on a sliding window.

    Parameters
    ----------
    df : pandas.DataFrame
        Dataset containing both features and target.
    predictor : TabularPredictor
        Trained AutoGluon TabularPredictor.
    feature_cols : list-like
        Names of the feature columns.
    target_col : str
        Name of the target column.
    window_size : int
        Number of latest samples to use as retraining window.

    Returns
    -------
    predictor : TabularPredictor
        The (possibly) retrained predictor.
    drift_log : pandas.DataFrame
        Log of drift and retraining events (one row per detected drift).
    metrics : dict
        Overall performance and timing metrics for the drift-monitoring phase.
    """
    # ADWIN drift detector (more sensitive with smaller clock)
    n_rows = len(df)
    print(f"[Drift] Step 1: Starting drift monitoring — {n_rows} rows, target={target_col}, window_size={window_size}")
    adwin = ADWIN(delta=0.01, clock=1)
    window_rows = deque(maxlen=window_size)
    events = []  # to log drift + retraining info

    # For metrics
    y_true_all = []
    y_pred_all = []
    correct_count = 0
    total_count = 0
    window_y_true = deque(maxlen=window_size)
    window_y_pred = deque(maxlen=window_size)
    total_retrain_time = 0.0

    # Time when monitoring started
    start_time = time.time()
    log_interval = max(1, n_rows // 10)

    for i, row in df.iterrows():
        y_true = row[target_col]
        y_pred = predict_autogluon(predictor, row, feature_cols)
        error = 0.0 if y_pred == y_true else 1.0

        # Update basic counts
        total_count += 1
        if y_pred == y_true:
            correct_count += 1
        y_true_all.append(y_true)
        y_pred_all.append(y_pred)
        window_y_true.append(y_true)
        window_y_pred.append(y_pred)

        # Update ADWIN with the current error (0 = correct, 1 = wrong)
        adwin.update(error)

        # Maintain the sliding window (store full rows)
        window_rows.append(row)

        # Report elapsed time since monitoring started
        elapsed = time.time() - start_time

        # Progress logging
        if (i + 1) % log_interval == 0 or i == 0:
            acc = correct_count / total_count if total_count else 0
            print(f"[Drift] Step 2: Progress row {i + 1}/{n_rows} — cumulative_accuracy={acc:.4f}, window_fill={len(window_rows)}")

        # Check if ADWIN signaled a drift after this update
        if adwin.drift_detected:
            print(f"[Drift] Step 3: *** CONCEPT DRIFT DETECTED *** at index {i} (elapsed={elapsed:.2f}s). Retraining on last {len(window_rows)} samples.")
            window_df = pd.DataFrame(list(window_rows))

            # Measure retraining time
            retrain_start = time.time()
            path = str(f"autogluon_models/utils/predictor.pkl") #predictor.path if hasattr(predictor, "path") else "autogluon_drift"
            predictor = TabularPredictor(label=target_col, path=path).fit(train_data=window_df)
            retrain_time = time.time() - retrain_start
            total_retrain_time += retrain_time
            print(f"[Drift] Step 4: Retrain completed in {retrain_time:.4f}s. Model saved to path={path}")

            events.append({
                "index": i,
                "elapsed_seconds": elapsed,
                "window_size": len(window_rows),
                "retrain_time_seconds": retrain_time,
            })

    # Build drift log
    drift_log = pd.DataFrame(events)
    n_drifts = len(events)
    total_runtime = time.time() - start_time
    print(f"[Drift] Step 5: Monitoring complete. Drifts detected={n_drifts}, total_retrain_time={total_retrain_time:.2f}s, runtime={total_runtime:.2f}s")
    if n_drifts == 0:
        print("[Drift] No concept drift was detected in this run (no retrain occurred).")

    # Compute metrics
    if total_count > 0:
        cumulative_accuracy = correct_count / total_count
    else:
        cumulative_accuracy = float("nan")

    def _as_classification_targets(y_true, y_pred):
        """Ensure both are discrete for sklearn classification metrics (no mix of multiclass and continuous)."""
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        # If predictions are float, round to int so sklearn treats them as class labels not continuous
        if np.issubdtype(y_pred.dtype, np.floating):
            y_pred = np.round(y_pred).astype(int)
        # If one is string and one is numeric, convert both to string for consistent multiclass comparison
        if y_true.dtype.kind in ("U", "O", "S") or y_pred.dtype.kind in ("U", "O", "S"):
            return np.array([str(x) for x in y_true]), np.array([str(x) for x in y_pred])
        return y_true, y_pred

    if y_true_all:
        yt, yp = _as_classification_targets(y_true_all, y_pred_all)
        final_accuracy = accuracy_score(yt, yp)
        f1 = f1_score(yt, yp, average="weighted", zero_division=0)
        precision = precision_score(yt, yp, average="weighted", zero_division=0)
        recall = recall_score(yt, yp, average="weighted", zero_division=0)
    else:
        final_accuracy = f1 = precision = recall = float("nan")

    if window_y_true:
        yt, yp = _as_classification_targets(list(window_y_true), list(window_y_pred))
        final_window_accuracy = accuracy_score(yt, yp)
    else:
        final_window_accuracy = float("nan")

    total_drifts = len(events)

    metrics = {
        "cumulative_accuracy": cumulative_accuracy,
        "final_accuracy": final_accuracy,
        "final_window_accuracy": final_window_accuracy,
        "f1_score": f1,
        "precision": precision,
        "recall": recall,
        "total_drifts": total_drifts,
        "total_retrain_time_seconds": total_retrain_time,
        "total_runtime_seconds": total_runtime,
    }

    return predictor, drift_log, metrics


# Example usage:
print("[AutoCDD] Loading CSV...")
df = load_csv("train.csv")
if df is not None:
    # Check sample-to-feature ratio
    num_samples = df.shape[0]
    num_features = df.shape[1] - 1  # last column assumed to be target
    print(f"[AutoCDD] Dataset: {num_samples} samples, {num_features} features (last column = target)")

    if num_samples <= (num_features + 1) * 10:
        print(f"Dataset size is small: {num_samples} samples vs {num_features + 1} total columns")
    else:
        # Split data: 70% train, 15% test, 15% drift monitoring
        n = len(df)
        n_train = int(0.7 * n) # 31.718,4
        n_test = int(0.15 * n) # 6.796,8
        n_drift = n - n_train - n_test # 6.796,8
        print(f"[AutoCDD] Split: train={n_train}, test={n_test}, drift={n_drift}")

        df_train = df.iloc[:n_train]
        df_test = df.iloc[n_train:n_train + n_test]
        df_drift = df.iloc[n_train + n_test:]

        # Define features and target
        feature_cols = df.columns[:-1]  # all columns except last as features
        target_col = df.columns[-1]     # last column as target
        print(f"[AutoCDD] Target column: {target_col}")

        # Train AutoGluon TabularPredictor on 70% of the data
        train_data = df_train[feature_cols.tolist() + [target_col]]
        print("[AutoCDD] Loading pre-trained predictor from 'autogluon_models'...")
        predictor = TabularPredictor.load(
            "autogluon_models",
            require_version_match=False,
            require_py_version_match=False,
        )
        print("[AutoCDD] Predictor loaded.")
        # predictor = TabularPredictor(label=target_col, path="autogluon_models").fit(
        #     train_data=train_data,
        #     presets="medium_quality_faster_train",
        #     time_limit=600,
        # )
        #
        #
        # simple test evaluation on 15% test split
        print("[AutoCDD] Evaluating on 15% test hold-out...")
        test_data = df_test[feature_cols.tolist() + [target_col]]
        if len(test_data) > 0:
            y_test = test_data[target_col]
            y_pred = predictor.predict(test_data[feature_cols])
            test_accuracy = (y_pred == y_test).mean()
            print(f"[AutoCDD] Test accuracy on 15% hold-out: {test_accuracy:.4f}")

        # Use the remaining 15% of data for concept drift detection and adaptive retraining
        print("[AutoCDD] Starting concept drift detection on 15% drift split...")
        predictor, drift_log, metrics = monitor_drift_and_retrain(
            df= df_drift,#pd.concat([df_test, df_drift], ignore_index=True),#df_drift,
            predictor=predictor,
            feature_cols=feature_cols,
            target_col=target_col,
            window_size=100,
        )
        fa = metrics.get("final_accuracy", float("nan"))
        fa_str = f"{fa:.4f}" if isinstance(fa, (int, float)) and not np.isnan(fa) else "nan"
        print(f"[AutoCDD] Drift phase done. Drifts detected: {len(drift_log)}, final_accuracy={fa_str}")

        # Save drift log and metrics to CSV
        print("[AutoCDD] Saving drift_log.csv and metrics_summary.csv...")
        drift_log.to_csv("drift_log.csv", index=False)
        metrics_df = pd.DataFrame([metrics])
        metrics_df.to_csv("metrics_summary.csv", index=False)

        # === Visualizations ===
        # 1) Drift log visualizations
        if not drift_log.empty:
            print("[AutoCDD] Showing drift visualizations (close window to continue)...")
            # Retraining time per drift
            plt.figure()
            plt.plot(drift_log["index"], drift_log["retrain_time_seconds"], marker="o")
            plt.xlabel("Sample index")
            plt.ylabel("Retrain time (s)")
            plt.title("Retraining time per detected drift")
            plt.grid(True)
            plt.tight_layout()
            plt.show()

            # Elapsed monitoring time at each drift
            plt.figure()
            plt.plot(drift_log["index"], drift_log["elapsed_seconds"], marker="o")
            plt.xlabel("Sample index")
            plt.ylabel("Elapsed time since start (s)")
            plt.title("Elapsed monitoring time at each detected drift")
            plt.grid(True)
            plt.tight_layout()
            plt.show()

        # 2) Metrics visualizations
        metrics_to_plot = [
            "cumulative_accuracy",
            "final_accuracy",
            "final_window_accuracy",
            "f1_score",
            "precision",
            "recall",
        ]
        values = [metrics[m] for m in metrics_to_plot]

        print("[AutoCDD] Showing metrics summary (close window to exit)...")
        plt.figure()
        plt.bar(metrics_to_plot, values)
        plt.xticks(rotation=45)
        plt.ylabel("Score")
        plt.title("Performance metrics summary")
        plt.tight_layout()
        plt.show()
