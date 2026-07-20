"""Psychology services — modularized into 8 functional sub-packages.

For backward compatibility, all public APIs are re-exported here.
New code should import from the sub-packages directly:
  from services.memory.search import search_similar
  from services.identity.prompt import build_time_context
  from services.emotion.affect import get_affect
  from services.cognition.state_machine import determine_mode
  from services.reflection.diary import generate_diary
"""

from services.memory import *
from services.identity import *
from services.emotion import *
from services.cognition import *
from services.reflection import *
from services.info import *
