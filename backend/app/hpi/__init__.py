"""Historical Pattern Intelligence (HPI).

User-controlled derivative & historical data module:
  - Fixed 7-derivative universe (see constants.HPI_UNIVERSE)
  - User-controlled selection, historical periods, sampling intervals
  - Storage-budget protection (target <= 150 MB, hard ceiling 200 MB)
  - Explicit, audited, scope-isolated deletion with confirmation
  - Coverage-aware pattern engine (never assumes a fixed 2-year history)
"""
