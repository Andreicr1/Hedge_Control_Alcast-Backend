from datetime import date

import pytest

from app.services import rfq_engine

# =============================================================================
# Basic Functionality Tests
# =============================================================================


def test_forward_fix_payoff_and_ppt():
    """Forward with Fix leg should include payoff text and correct PPT."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.FIX,
            quantity_mt=10,
            fixing_date=date(2024, 1, 2),  # Tuesday
        ),
    )
    text = rfq_engine.generate_rfq_text(
        trade=trade, cal=cal, company_header=None, company_label_for_payoff="Alcast"
    )

    assert "How can I Buy 10 mt Al USD ppt 04/01/24?" in text
    assert (
        "Expected Payoff:\nIf the official price of 02/01/24 is higher than the Fixed Price, Alcast receives the difference. "
        "If the official price is lower, Alcast pays the difference."
    ) in text


# =============================================================================
# Swap Tests - Most Common Use Case
# =============================================================================


def test_swap_avg_plus_fix():
    """Swap AVG + Fix: most common trade type."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.SWAP,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=500,
            month_name="March",
            year=2025,
        ),
        leg2=rfq_engine.Leg(
            side=rfq_engine.Side.SELL,
            price_type=rfq_engine.PriceType.FIX,
            quantity_mt=500,
        ),
        sync_ppt=True,
    )
    text = rfq_engine.generate_rfq_text(trade=trade, cal=cal, company_header="Alcast Brasil")

    # Should have company header
    assert "Alcast Brasil" in text
    # Should have Buy AVG leg
    assert "Buy 500 mt Al AVG March 2025" in text
    # Should have Sell Fix leg
    assert "Sell 500 mt Al USD" in text


def test_swap_avg_plus_c2r():
    """Swap AVG + C2R trade."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.SWAP,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=250,
            month_name="April",
            year=2025,
        ),
        leg2=rfq_engine.Leg(
            side=rfq_engine.Side.SELL,
            price_type=rfq_engine.PriceType.C2R,
            quantity_mt=250,
            fixing_date=date(2025, 4, 15),
        ),
    )
    text = rfq_engine.generate_rfq_text(trade=trade, cal=cal)

    assert "Buy 250 mt Al AVG April 2025" in text
    assert "C2R" in text or "Official Settlement Price" in text


# =============================================================================
# PPT Calculation Tests
# =============================================================================


def test_ppt_avg_second_business_day_of_next_month():
    """AVG PPT should be 2nd business day of next month."""
    cal = rfq_engine.HolidayCalendar()
    leg = rfq_engine.Leg(
        side=rfq_engine.Side.BUY,
        price_type=rfq_engine.PriceType.AVG,
        quantity_mt=100,
        month_name="January",
        year=2025,
    )
    ppt = rfq_engine.compute_ppt_for_leg(leg, cal)
    # January 2025 -> PPT should be 2nd business day of February 2025
    # Feb 1, 2025 is Saturday, Feb 3 is Monday (1st BD), Feb 4 is Tuesday (2nd BD)
    assert ppt == date(2025, 2, 4)


def test_ppt_avginter_two_business_days_after_end():
    """AVGInter PPT should be 2 business days after end_date."""
    cal = rfq_engine.HolidayCalendar()
    leg = rfq_engine.Leg(
        side=rfq_engine.Side.BUY,
        price_type=rfq_engine.PriceType.AVG_INTER,
        quantity_mt=100,
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 15),  # Saturday
    )
    ppt = rfq_engine.compute_ppt_for_leg(leg, cal)
    # March 15, 2025 is Saturday, +2 BD = March 18 (Tue)
    assert ppt == date(2025, 3, 18)


def test_ppt_c2r_two_business_days_after_fixing():
    """C2R PPT should be 2 business days after fixing_date."""
    cal = rfq_engine.HolidayCalendar()
    leg = rfq_engine.Leg(
        side=rfq_engine.Side.SELL,
        price_type=rfq_engine.PriceType.C2R,
        quantity_mt=100,
        fixing_date=date(2025, 3, 10),  # Monday
    )
    ppt = rfq_engine.compute_ppt_for_leg(leg, cal)
    # March 10, 2025 is Monday, +2 BD = March 12 (Wed)
    assert ppt == date(2025, 3, 12)


def test_compute_trade_ppt_dates():
    """compute_trade_ppt_dates should return correct PPT for both legs."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.SWAP,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=100,
            month_name="March",
            year=2025,
        ),
        leg2=rfq_engine.Leg(
            side=rfq_engine.Side.SELL,
            price_type=rfq_engine.PriceType.FIX,
            quantity_mt=100,
        ),
        sync_ppt=True,
    )
    result = rfq_engine.compute_trade_ppt_dates(trade, cal)

    assert "leg1_ppt" in result
    assert "leg2_ppt" in result
    assert "trade_ppt" in result
    assert result["leg1_ppt"] is not None
    # trade_ppt should be max of both leg PPTs
    assert result["trade_ppt"] is not None


# =============================================================================
# Validation Tests
# =============================================================================


def test_validate_avg_requires_month_year():
    """AVG price type requires month_name and year."""
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=100,
            # Missing month_name and year
        ),
    )
    errors = rfq_engine.validate_trade(trade)
    assert len(errors) > 0
    assert any("AVG" in e.message for e in errors)


def test_validate_avginter_requires_dates():
    """AVGInter price type requires start_date and end_date."""
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG_INTER,
            quantity_mt=100,
            # Missing start_date and end_date
        ),
    )
    errors = rfq_engine.validate_trade(trade)
    assert len(errors) > 0
    assert any("AVGInter" in e.message for e in errors)


def test_validate_c2r_requires_fixing_date():
    """C2R price type requires fixing_date."""
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.C2R,
            quantity_mt=100,
            # Missing fixing_date
        ),
    )
    errors = rfq_engine.validate_trade(trade)
    assert len(errors) > 0
    assert any("fixing" in e.message.lower() for e in errors)


def test_validate_quantity_must_be_positive():
    """Quantity must be greater than zero."""
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=0,  # Invalid
            month_name="March",
            year=2025,
        ),
    )
    errors = rfq_engine.validate_trade(trade)
    assert len(errors) > 0
    assert any("zero" in e.message.lower() or "positive" in e.message.lower() for e in errors)


def test_validate_avginter_bad_range():
    """AVGInter start_date must be <= end_date."""
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG_INTER,
            quantity_mt=100,
            start_date=date(2025, 3, 20),  # After end_date
            end_date=date(2025, 3, 10),
        ),
    )
    errors = rfq_engine.validate_trade(trade)
    assert len(errors) > 0
    assert any("range" in e.message.lower() or "start" in e.message.lower() for e in errors)


# =============================================================================
# Execution Instruction Tests
# =============================================================================


def test_execution_instruction_limit():
    """Limit order instruction should be formatted correctly."""
    order = rfq_engine.OrderInstruction(
        order_type=rfq_engine.OrderType.LIMIT,
        limit_price="2450",
        validity="Day",
    )
    text = rfq_engine.build_execution_instruction(order, rfq_engine.Side.BUY)

    assert "Limit" in text
    assert "2450" in text
    assert "Day" in text


def test_execution_instruction_resting_buy():
    """Resting order for BUY should use 'best offer'."""
    order = rfq_engine.OrderInstruction(
        order_type=rfq_engine.OrderType.RESTING,
        validity="Day",
    )
    text = rfq_engine.build_execution_instruction(order, rfq_engine.Side.BUY)

    assert "best offer" in text


def test_execution_instruction_resting_sell():
    """Resting order for SELL should use 'best bid'."""
    order = rfq_engine.OrderInstruction(
        order_type=rfq_engine.OrderType.RESTING,
        validity="Day",
    )
    text = rfq_engine.build_execution_instruction(order, rfq_engine.Side.SELL)

    assert "best bid" in text


def test_swap_with_limit_order():
    """Swap with Limit order should include execution instruction."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.SWAP,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=500,
            month_name="April",
            year=2025,
            order=rfq_engine.OrderInstruction(
                order_type=rfq_engine.OrderType.LIMIT,
                limit_price="2450",
                validity="GTC",
            ),
        ),
        leg2=rfq_engine.Leg(
            side=rfq_engine.Side.SELL,
            price_type=rfq_engine.PriceType.FIX,
            quantity_mt=500,
        ),
        sync_ppt=True,
    )
    text = rfq_engine.generate_rfq_text(trade=trade, cal=cal)

    assert "Execution Instruction" in text
    assert "Limit" in text
    assert "2450" in text


# =============================================================================
# Expected Payoff Tests
# =============================================================================


def test_expected_payoff_avg_vs_fix_buy_avg():
    """Payoff text for Buy AVG / Sell Fix should be correct."""
    cal = rfq_engine.HolidayCalendar()
    fixed_leg = rfq_engine.Leg(
        side=rfq_engine.Side.SELL,
        price_type=rfq_engine.PriceType.FIX,
        quantity_mt=500,
    )
    avg_leg = rfq_engine.Leg(
        side=rfq_engine.Side.BUY,
        price_type=rfq_engine.PriceType.AVG,
        quantity_mt=500,
        month_name="March",
        year=2025,
    )

    payoff = rfq_engine.build_expected_payoff_text(
        fixed_leg=fixed_leg,
        other_leg=avg_leg,
        cal=cal,
        company_label="Alcast",
    )

    assert "Expected Payoff" in payoff
    assert "Alcast" in payoff
    assert "March 2025" in payoff


def test_expected_payoff_sell_avg_buy_fix():
    """Payoff direction should be correct for Sell AVG / Buy Fix."""
    cal = rfq_engine.HolidayCalendar()
    fixed_leg = rfq_engine.Leg(
        side=rfq_engine.Side.BUY,
        price_type=rfq_engine.PriceType.FIX,
        quantity_mt=500,
    )
    avg_leg = rfq_engine.Leg(
        side=rfq_engine.Side.SELL,
        price_type=rfq_engine.PriceType.AVG,
        quantity_mt=500,
        month_name="March",
        year=2025,
    )

    payoff = rfq_engine.build_expected_payoff_text(
        fixed_leg=fixed_leg,
        other_leg=avg_leg,
        cal=cal,
        company_label="Company",
    )

    assert "Expected Payoff" in payoff
    # When fixed_leg is BUY, if average > fixed: company pays
    assert "Company" in payoff


# =============================================================================
# Holiday Calendar Tests
# =============================================================================


def test_holiday_calendar_weekend():
    """Weekend days should not be business days."""
    cal = rfq_engine.HolidayCalendar()
    # Jan 4, 2025 is Saturday
    assert not cal.is_business_day(date(2025, 1, 4))
    # Jan 5, 2025 is Sunday
    assert not cal.is_business_day(date(2025, 1, 5))
    # Jan 6, 2025 is Monday
    assert cal.is_business_day(date(2025, 1, 6))


def test_holiday_calendar_with_holidays():
    """Holidays should not be business days."""
    cal = rfq_engine.HolidayCalendar(holidays_iso=["2025-01-01"])
    # New Year's Day
    assert not cal.is_business_day(date(2025, 1, 1))


def test_add_business_days_skips_weekends():
    """add_business_days should skip weekends."""
    cal = rfq_engine.HolidayCalendar()
    # Friday Jan 3, 2025 + 2 BD = Tuesday Jan 7, 2025
    result = rfq_engine.add_business_days(date(2025, 1, 3), 2, cal)
    assert result == date(2025, 1, 7)


# =============================================================================
# Forward Trade Tests
# =============================================================================


def test_forward_single_leg():
    """Forward with single leg should generate correct text."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG_INTER,
            quantity_mt=250,
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 15),
        ),
    )
    text = rfq_engine.generate_rfq_text(trade=trade, cal=cal, company_header="Alcast Trading")

    assert "How can I Buy" in text
    assert "250 mt" in text
    assert "AVG" in text


def test_forward_two_legs_sync_ppt():
    """Forward with two legs and sync_ppt should generate two questions."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=100,
            month_name="March",
            year=2025,
        ),
        leg2=rfq_engine.Leg(
            side=rfq_engine.Side.SELL,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=100,
            month_name="April",
            year=2025,
        ),
        sync_ppt=True,
    )
    text = rfq_engine.generate_rfq_text(trade=trade, cal=cal)

    # Should have two "How can I" questions
    assert text.count("How can I") == 2


# =============================================================================
# Edge Cases
# =============================================================================


def test_generate_rfq_text_raises_on_validation_error():
    """generate_rfq_text should raise ValueError on validation errors."""
    cal = rfq_engine.HolidayCalendar()
    trade = rfq_engine.RfqTrade(
        trade_type=rfq_engine.TradeType.FORWARD,
        leg1=rfq_engine.Leg(
            side=rfq_engine.Side.BUY,
            price_type=rfq_engine.PriceType.AVG,
            quantity_mt=100,
            # Missing month_name and year
        ),
    )

    with pytest.raises(ValueError):
        rfq_engine.generate_rfq_text(trade=trade, cal=cal)


def test_fmt_qty_integer():
    """Quantities that are integers should be formatted without decimals."""
    assert rfq_engine.fmt_qty(500) == "500"
    assert rfq_engine.fmt_qty(500.0) == "500"


def test_fmt_qty_decimal():
    """Quantities with decimals should be formatted correctly."""
    assert rfq_engine.fmt_qty(500.5) == "500.5"
    assert rfq_engine.fmt_qty(500.25) == "500.25"


def test_side_verb():
    """Side enum should return correct verb."""
    assert rfq_engine.Side.BUY.verb() == "Buy"
    assert rfq_engine.Side.SELL.verb() == "Sell"
