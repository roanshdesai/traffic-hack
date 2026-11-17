"""Early detection of overcrowding (the main product).

Turns people-count signals (camera counter output, ticket samples, manual
counts) into a per-site, per-time-window status, a short-horizon forecast and
an early warning. Road traffic is kept as a separate context signal.

Nothing here is verified real-world crowding: counts are estimates or samples,
and every result says which.
"""
