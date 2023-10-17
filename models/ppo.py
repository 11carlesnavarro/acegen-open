from pathlib import Path
import torch
from tensordict.nn import TensorDictModule, TensorDictSequential
from torchrl.modules import (
    MLP,
    LSTMModule,
    ValueOperator,
    ActorValueOperator,
    ProbabilisticActor,
)
from torchrl.envs import ExplorationType


class Embed(torch.nn.Module):
    """Implements a simple embedding layer."""

    def __init__(self, input_size, embedding_size):
        super().__init__()
        self.input_size = input_size
        self.embedding_size = embedding_size
        self._embedding = torch.nn.Embedding(input_size, embedding_size)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        *batch, L = inputs.shape
        if len(batch) > 1:
            inputs = inputs.flatten(0, len(batch) - 1)
        out = self._embedding(inputs)
        if len(batch) > 1:
            out = out.unflatten(0, batch)
        out = out.squeeze(
            -1
        )  # If time dimension is 1, remove it. Ugly hack, should not be necessary
        out = out.squeeze(
            -2
        )  # If time dimension is 1, remove it. Ugly hack, should not be necessary
        return out


def create_shared_ppo_models(vocabulary_size):
    """Create a shared PPO model using architecture and weights from the
    "REINVENT 2.0 – an AI tool for de novo drug design" paper.

    The policy component of the model uses the same architecture and weights
    as described in the original paper. The critic component is implemented
    as a simple Multi-Layer Perceptron (MLP) with one output.

    Returns:
    - shared_model: The shared PPO model with both policy and critic components.

    Example:
    ```python
    shared_model = create_shared_ppo_model(10)
    ```
    """

    embedding_module = TensorDictModule(
        Embed(vocabulary_size, 256),
        in_keys=["observation"],
        out_keys=["embed"],
    )
    lstm_module = LSTMModule(
        input_size=256,
        hidden_size=512,
        num_layers=3,
        in_keys=["embed", "recurrent_state_h", "recurrent_state_c"],
        out_keys=[
            "features",
            ("next", "recurrent_state_h"),
            ("next", "recurrent_state_c"),
        ],
    )
    actor_model = TensorDictModule(
        MLP(
            in_features=512,
            out_features=vocabulary_size,
            num_cells=[],
        ),
        in_keys=["features"],
        out_keys=["logits"],
    )
    policy_module = ProbabilisticActor(
        module=actor_model,
        in_keys=["logits"],
        out_keys=["action"],
        distribution_class=torch.distributions.Categorical,
        return_log_prob=True,
        default_interaction_type=ExplorationType.RANDOM,
    )

    critic_module = ValueOperator(
        MLP(
            in_features=512,
            out_features=1,
            num_cells=[],
        ),
        in_keys=["features"],
    )

    # Wrap modules in a single ActorCritic operator
    actor_critic_inference = ActorValueOperator(
        common_operator=TensorDictSequential(embedding_module, lstm_module),
        policy_operator=policy_module,
        value_operator=critic_module,
    )

    actor_critic_training = ActorValueOperator(
        common_operator=TensorDictSequential(
            embedding_module, lstm_module.set_recurrent_mode(True)
        ),
        policy_operator=policy_module,
        value_operator=critic_module,
    )

    actor_inference = actor_critic_inference.get_policy_operator()
    critic_inference = actor_critic_inference.get_value_operator()
    actor_training = actor_critic_training.get_policy_operator()
    critic_training = actor_critic_training.get_value_operator()
    transform = lstm_module.make_tensordict_primer()

    ckpt = torch.load(Path(__file__).resolve().parent / "priors" / "actor_critic.prior")
    actor_inference.load_state_dict(ckpt)
    actor_training.load_state_dict(ckpt)

    return actor_inference, actor_training, critic_inference, critic_training, transform