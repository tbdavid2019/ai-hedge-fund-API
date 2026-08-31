import unittest
import numpy as np
import pandas as pd
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quant.risk import (
    calculate_var_cvar,
    calculate_volatility_metrics,
    calculate_risk_adjusted_position_size,
)
from src.quant.valuation import (
    calculate_dcf_sensitivity,
    calculate_altman_z_score,
    calculate_piotroski_f_score,
)
from src.quant.technicals import (
    calculate_amihud_illiquidity,
    calculate_atr_dynamic_stops,
)


class TestQuantModule(unittest.TestCase):
    def test_var_cvar_calculation(self):
        np.random.seed(42)
        daily_returns = pd.Series(np.random.normal(0.001, 0.02, 100))
        metrics = calculate_var_cvar(daily_returns)
        self.assertEqual(metrics["status"], "calculated")
        self.assertIn("var_95", metrics)
        self.assertIn("cvar_95", metrics)
        self.assertGreater(metrics["var_95"], 0)
        self.assertGreaterEqual(metrics["cvar_95"], metrics["var_95"])
        self.assertGreater(metrics["volatility_annualized"], 0)

    def test_risk_adjusted_position_sizing(self):
        result = calculate_risk_adjusted_position_size(
            total_portfolio_value=100000.0,
            available_cash=50000.0,
            current_price=150.0,
            cvar_95=0.06,
            annualized_vol=0.35,
            max_risk_budget_ratio=0.02,
            base_position_limit_ratio=0.25,
        )
        self.assertGreater(result["recommended_position_dollars"], 0)
        self.assertLessEqual(result["recommended_position_dollars"], 50000.0)
        self.assertGreater(result["recommended_shares"], 0)
        self.assertIn("binding_constraint", result)

    def test_dcf_sensitivity_matrix(self):
        dcf = calculate_dcf_sensitivity(
            free_cash_flow=10_000_000.0,
            current_price=100.0,
            shares_outstanding=1_000_000.0,
            base_wacc=0.10,
            base_terminal_growth=0.025,
            forecast_growth=0.08,
        )
        self.assertEqual(dcf["status"], "calculated")
        self.assertEqual(len(dcf["sensitivity_matrix"]), 5)
        self.assertGreater(dcf["fair_value_median"], 0)
        self.assertIn("valuation_status", dcf)

    def test_altman_z_score(self):
        z_res = calculate_altman_z_score(
            working_capital=500_000.0,
            total_assets=2_000_000.0,
            retained_earnings=600_000.0,
            ebit=400_000.0,
            market_cap=3_000_000.0,
            total_liabilities=800_000.0,
            total_revenue=2_500_000.0,
        )
        self.assertIsNotNone(z_res["z_score"])
        self.assertGreater(z_res["z_score"], 2.0)
        self.assertIn(z_res["risk_level"], ["Low", "Moderate", "High"])

    def test_piotroski_f_score(self):
        curr = {
            "net_income": 100000.0,
            "return_on_assets": 0.12,
            "operating_cash_flow": 150000.0,
            "current_ratio": 2.1,
            "gross_margin": 0.45,
            "debt_to_equity": 0.5,
        }
        prev = {
            "current_ratio": 1.8,
            "gross_margin": 0.40,
            "debt_to_equity": 0.6,
        }
        f_res = calculate_piotroski_f_score(curr, prev)
        self.assertGreaterEqual(f_res["f_score"], 5)
        self.assertEqual(f_res["max_score"], 9)

    def test_amihud_illiquidity_and_atr(self):
        dates = pd.date_range("2026-01-01", periods=30)
        df = pd.DataFrame(
            {
                "close": [100.0 + i for i in range(30)],
                "high": [101.0 + i for i in range(30)],
                "low": [99.0 + i for i in range(30)],
                "volume": [1_000_000 for _ in range(30)],
            },
            index=dates,
        )

        amihud = calculate_amihud_illiquidity(df)
        self.assertIn("amihud_illiquidity_ratio", amihud)
        self.assertIn("liquidity_tier", amihud)

        atr = calculate_atr_dynamic_stops(df)
        self.assertGreater(atr["atr_14"], 0)
        self.assertLess(atr["trailing_stop_long"], df["close"].iloc[-1])


if __name__ == "__main__":
    unittest.main()
