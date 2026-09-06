"""Statistical Evaluator for the Research Laboratory (§21).

Calculates sample size, accuracy, precision, recall, F1, MFE/MAE means,
95% confidence intervals (Wilson score interval), and hypothesis tests (p-values)
against naive baselines.
"""

import math
from typing import Dict, List, Tuple
from app.research.enums import Direction
from app.research.models import PredictionOutcome, ResearchPrediction, ValidationReport


class StatisticalEvaluator:
    """Evaluates prediction performance with rigorous statistical bounds."""

    @classmethod
    def calculate_confidence_interval(cls, successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
        """Wilson score interval for binomial proportions with 95% confidence."""
        if total == 0:
            return 0.0, 0.0
        p_hat = successes / total
        denominator = 1.0 + (z ** 2) / total
        center = (p_hat + (z ** 2) / (2 * total)) / denominator
        margin = z * math.sqrt((p_hat * (1 - p_hat) + (z ** 2) / (4 * total)) / total) / denominator
        low = max(0.0, center - margin)
        high = min(1.0, center + margin)
        return round(low * 100.0, 2), round(high * 100.0, 2)

    @classmethod
    def calculate_p_value(cls, observed_acc: float, baseline_acc: float, n: int) -> float:
        """One-tailed z-test for proportion difference against baseline."""
        if n == 0 or baseline_acc in (0.0, 1.0):
            return 1.0
        p0 = baseline_acc
        p = observed_acc
        se = math.sqrt(p0 * (1 - p0) / n)
        if se == 0:
            return 1.0
        z_stat = (p - p0) / se
        # Standard normal CDF approximation (Abramowitz and Stegun)
        def std_norm_cdf(x: float) -> float:
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
        p_val = 1.0 - std_norm_cdf(z_stat)
        return max(0.0001, min(1.0, round(p_val, 4)))

    @classmethod
    def evaluate(
        cls,
        predictions: List[ResearchPrediction],
        outcomes: List[PredictionOutcome],
        baseline_accuracy: float = 0.50,
        regimes: Dict[str, str] = None,
        sessions: Dict[str, str] = None,
    ) -> ValidationReport:
        """Run complete statistical evaluation."""
        total = len(predictions)
        if total == 0:
            return ValidationReport(
                sample_size=0,
                accuracy=0.0,
                precision=0.0,
                recall=0.0,
                f1_score=0.0,
                mfe_mean=0.0,
                mae_mean=0.0,
                win_loss_ratio=0.0,
                baseline_accuracy=round(baseline_accuracy * 100.0, 2),
                excess_accuracy=0.0,
                confidence_interval_95=(0.0, 0.0),
                p_value=1.0,
                is_statistically_significant=False,
                regime_breakdown={},
                session_breakdown={},
            )

        outcome_map = {o.prediction_id: o for o in outcomes}
        correct_count = 0
        tp = 0  # Predicted bullish & actual bullish
        fp = 0  # Predicted bullish & actual bearish
        fn = 0  # Predicted bearish & actual bullish
        tn = 0  # Predicted bearish & actual bearish

        mfes: List[float] = []
        maes: List[float] = []

        # Breakdown dictionaries: {group: {"total": int, "correct": int}}
        regime_stats: Dict[str, Dict[str, int]] = {}
        session_stats: Dict[str, Dict[str, int]] = {}

        for p in predictions:
            o = outcome_map.get(p.prediction_id)
            if not o:
                continue

            if o.is_correct:
                correct_count += 1

            mfes.append(o.mfe)
            maes.append(o.mae)

            if p.direction == Direction.BULLISH:
                if o.actual_direction == Direction.BULLISH:
                    tp += 1
                else:
                    fp += 1
            elif p.direction == Direction.BEARISH:
                if o.actual_direction == Direction.BULLISH:
                    fn += 1
                else:
                    tn += 1

            # Regimes
            reg = regimes.get(p.prediction_id, "UNKNOWN") if regimes else "UNKNOWN"
            if reg not in regime_stats:
                regime_stats[reg] = {"total": 0, "correct": 0}
            regime_stats[reg]["total"] += 1
            if o.is_correct:
                regime_stats[reg]["correct"] += 1

            # Sessions
            sess = sessions.get(p.prediction_id, "UNKNOWN") if sessions else "UNKNOWN"
            if sess not in session_stats:
                session_stats[sess] = {"total": 0, "correct": 0}
            session_stats[sess]["total"] += 1
            if o.is_correct:
                session_stats[sess]["correct"] += 1

        accuracy = round((correct_count / total) * 100.0, 2)
        precision = round((tp / (tp + fp)) * 100.0, 2) if (tp + fp) > 0 else 0.0
        recall = round((tp / (tp + fn)) * 100.0, 2) if (tp + fn) > 0 else 0.0
        f1 = round((2 * precision * recall / (precision + recall)), 2) if (precision + recall) > 0 else 0.0

        mfe_mean = round(sum(mfes) / len(mfes), 2) if mfes else 0.0
        mae_mean = round(sum(maes) / len(maes), 2) if maes else 0.0
        losses = total - correct_count
        win_loss_ratio = round(correct_count / losses, 2) if losses > 0 else float(correct_count)

        ci_low, ci_high = cls.calculate_confidence_interval(correct_count, total)
        p_val = cls.calculate_p_value(correct_count / total, baseline_accuracy, total)
        excess = round(accuracy - (baseline_accuracy * 100.0), 2)
        is_sig = p_val < 0.05 and excess > 0

        # Build breakdowns
        regime_breakdown = {
            r: {
                "sample_size": float(data["total"]),
                "accuracy": round((data["correct"] / data["total"]) * 100.0, 2) if data["total"] > 0 else 0.0,
            }
            for r, data in regime_stats.items()
        }

        session_breakdown = {
            s: {
                "sample_size": float(data["total"]),
                "accuracy": round((data["correct"] / data["total"]) * 100.0, 2) if data["total"] > 0 else 0.0,
            }
            for s, data in session_stats.items()
        }

        return ValidationReport(
            sample_size=total,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            mfe_mean=mfe_mean,
            mae_mean=mae_mean,
            win_loss_ratio=win_loss_ratio,
            baseline_accuracy=round(baseline_accuracy * 100.0, 2),
            excess_accuracy=excess,
            confidence_interval_95=(ci_low, ci_high),
            p_value=p_val,
            is_statistically_significant=is_sig,
            regime_breakdown=regime_breakdown,
            session_breakdown=session_breakdown,
        )
