-- 016 Restore authentic executed and expired signals from erroneous VOID quarantine
-- Unvoids legitimate executed signals that were quarantined due to missing outcome fields.

-- 1. Restore the 10 real executed trades with their factual exit status and PnL
UPDATE public.executed_signals
SET status = 'CLOSED',
    exit_reason = 'TIME_STOP_HIT',
    actual_pnl_inr = 452.18,
    actual_pnl_points = 26.9,
    is_winner = TRUE
WHERE signal_id = '6a65f1c9-6536-43e1-9ba1-f0c588877127';

UPDATE public.executed_signals
SET status = 'CLOSED',
    exit_reason = 'TIME_STOP_HIT',
    actual_pnl_inr = 1574.40,
    actual_pnl_points = 157.44,
    is_winner = TRUE
WHERE signal_id = 'c4764303-ed64-46e7-a246-552f9b8cf47e';

UPDATE public.executed_signals
SET status = 'CLOSED',
    exit_reason = 'TIME_STOP_HIT',
    actual_pnl_inr = 1848.60,
    actual_pnl_points = 184.86,
    is_winner = TRUE
WHERE signal_id = '13f71780-c2ea-4f39-9464-e3e7b63a66ff';

UPDATE public.executed_signals
SET status = 'CLOSED',
    exit_reason = 'TIME_STOP_HIT',
    actual_pnl_inr = 2657.30,
    actual_pnl_points = 265.73,
    is_winner = TRUE
WHERE signal_id = '4d7e6195-aea8-41c5-bfd3-bdf066bf8697';

UPDATE public.executed_signals
SET status = 'CLOSED',
    exit_reason = 'TARGET_2_HIT',
    actual_pnl_inr = 6143.00,
    actual_pnl_points = 82.84,
    is_winner = TRUE
WHERE signal_id = 'be7a401f-483c-491a-b9ac-f1b2dcc54014';

UPDATE public.executed_signals
SET status = 'CLOSED',
    exit_reason = 'TARGET_1_HIT',
    actual_pnl_inr = 1704.75,
    actual_pnl_points = 22.73,
    is_winner = TRUE
WHERE signal_id = '41adc22b-f751-456e-9873-1711981c9788';

UPDATE public.executed_signals
SET status = 'STOP_LOSS_HIT',
    exit_reason = 'STOP_LOSS_HIT',
    actual_pnl_inr = -462.00,
    actual_pnl_points = -23.1,
    is_winner = FALSE
WHERE signal_id = '5dafb8dc-a7db-43c5-971d-cbcf7bd248af';

UPDATE public.executed_signals
SET status = 'STOP_LOSS_HIT',
    exit_reason = 'STOP_LOSS_HIT',
    actual_pnl_inr = -286.62,
    actual_pnl_points = -22.92,
    is_winner = FALSE
WHERE signal_id = '14b3c58e-b9b3-4238-92c5-5a9e32dae7d4';

UPDATE public.executed_signals
SET status = 'STOP_LOSS_HIT',
    exit_reason = 'STOP_LOSS_HIT',
    actual_pnl_inr = -2528.36,
    actual_pnl_points = -122.98,
    is_winner = FALSE
WHERE signal_id = '6eb51645-1a28-4cec-8857-bf3132f303bd';

UPDATE public.executed_signals
SET status = 'STOP_LOSS_HIT',
    exit_reason = 'STOP_LOSS_HIT',
    actual_pnl_inr = -2528.36,
    actual_pnl_points = -61.49,
    is_winner = FALSE
WHERE signal_id = 'e06e5f41-85a1-4059-ba22-eebea4fb08bf';

-- 2. Restore any remaining untriggered voided signals to EXPIRED
UPDATE public.executed_signals
SET status = 'EXPIRED',
    exit_reason = COALESCE(exit_reason, 'EOD_EXPIRED')
WHERE status = 'VOID'
  AND actual_fill_price IS NULL;
