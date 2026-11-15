# Makes `import config`, `import traffic` work when running pytest from the project root.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
