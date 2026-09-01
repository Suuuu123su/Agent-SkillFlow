"""T16-E 第二模型一次性隐藏凭据入口。"""

import typer

from skillflow.experiment.t16.task_success_canary_cli import main_t16e

if __name__ == "__main__":
    typer.run(main_t16e)
