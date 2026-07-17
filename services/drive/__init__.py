"""Drive system — internal motivational forces driving AI behavior.

8 drive dimensions modelling the AI's inner motivational state:
miss, curiosity, care, playfulness, express, protect, fatigue, connection.

Each drive has a baseline, decays toward it over time (homeostasis),
and is stimulated by conversation signals. The dominant drive shapes
idle thoughts and influences behavioral mode selection.
"""

from services.drive.engine import (
    init_drive_db,
    get_drives,
    get_drive_values,
    get_dominant_drive,
    update_drives_on_chat,
    drive_heartbeat,
    get_drive_context,
    get_drive_thought_theme,
)
