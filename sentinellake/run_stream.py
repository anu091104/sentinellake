"""Entry point for spark-submit (which needs a file, not a module path)."""
from sentinellake.streaming.job import main

if __name__ == "__main__":
    main()
