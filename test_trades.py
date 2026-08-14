def test_sl_y_tp_mismo_grupo():
    active_trade = {
        "groups": {
            "BUY": {
                "sl": 950,
                "levels": [{"tp": 950, "rr": 1}],  # TP y SL en el mismo nivel
                "resolved": False
            }
        }
    }
    # Esta vela toca tanto el SL como el TP (low <= 950 y high >= 950)
    current_candle = {"high": 960, "low": 940}

    check_triggers(active_trade, current_candle)

    # Validación: el grupo debe cerrarse por SL, no por TP
    assert active_trade["groups"]["BUY"]["resolved"] is True, "El grupo BUY no se cerró"
    # El TP no debería marcarse como resuelto porque ganó el SL
    assert active_trade["groups"]["BUY"]["levels"][0].get("resolved") is not True, "El TP no debería ejecutarse"
