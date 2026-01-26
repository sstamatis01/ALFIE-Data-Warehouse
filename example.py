import logging
import uuid

from pydantic import BaseModel
from task_manager.core.kafka_messages import TaskFailure
from task_manager.worker import WorkerSettings, run_worker

logger = logging.getLogger(__name__)


# Pydantic model used to parse input
class MyTaskInput(BaseModel):
    foo_id: str


# Pydantic model used to serialize output
class MyTaskOutput(BaseModel):
    bar_id: str


# The implementation of your worker
async def do_work(input: MyTaskInput) -> tuple[MyTaskOutput | None, TaskFailure | None]:
    logger.info("Processing input:\n" + input.model_dump_json(indent=4))
    try:
        # Process input
        # foo = autodw.get_foo(input.foo_id)
        # ...processing

        # Preserve IDs of the new entities you create
        # bar = autodw.create_bar()
        # bar_id = bar.id

        bar_id = str(uuid.uuid4())  # Mock bar_id
    except Exception:
        # Send failure if unresolvable error occurred
        failure = TaskFailure(
            error_type="unexpected_error",
            error_message="Worker raised error unexpectedly",
        )
        return None, failure

    # Send output if succeeded
    output = MyTaskOutput(
        bar_id=bar_id,
    )
    return output, None


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    run_worker(
        do_work=do_work,
        settings=WorkerSettings(
            # You can pass the parameters directly or via environment variables
            # or by using .env file, which is automatically loaded.
            task_name="foo",
            kafka_consumer_group_id="alfie-foo",
        ),
        # Specify these parameters for Pydantic support. Otherwise, the engine
        # passes dict[str, Any] input and expects dict[str, Any] output.
        input_t=MyTaskInput,
        output_t=MyTaskOutput,
    )


if __name__ == "__main__":
    main()
