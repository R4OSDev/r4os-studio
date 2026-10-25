"""Fixed Skill Manager settings entry, with its own private SQLite setting."""
import json
import sys
from system_prompt import main
from store import ProjectFault


if __name__ == '__main__':
    try: main('skill')
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Skill Manager prompt storage is unavailable. Existing data was preserved.', 'code': 503})); sys.exit(1)
