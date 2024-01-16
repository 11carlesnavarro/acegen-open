from __future__ import annotations

import torch
from tensordict import TensorDict


def remove_duplicated_keys(tensordict: TensorDict, key: str) -> TensorDict:
    """Removes duplicate rows from a PyTorch tensor.

    Args:
    - tensordict (TensorDict): Input tensordict.
    - key (str): Key of the tensor to remove duplicate rows from.

    Returns:
    - TensorDict: Output tensordict with duplicate rows removed.
    """
    tensor = tensordict.get(key)

    _, unique_indices = torch.unique(tensor, dim=0, sorted=True, return_inverse=True)

    # Sort the unique indices
    unique_indices = torch.unique(unique_indices, dim=0)

    # Use torch.sort to ensure the output tensor maintains the order of rows in the input tensor
    unique_tensordict = tensordict[unique_indices]

    return unique_tensordict


def remove_keys_in_reference(reference_tensordict, target_tensordict, key):
    """Removes rows from the target tensor that are present in the reference tensor.

    Args:
    - tensordict (TensorDict): Reference TensorDict of shape (N, M).
    - target_tensordict (TensorDict): Target TensorDict of shape (L, M).
    - key (str): Key of the tensor to remove rows from.

    Returns:
    - TensorDict: Filtered target TensorDict containing rows not present in the reference tensor.
    """
    reference_tensor = reference_tensordict.get(key)
    target_tensor = target_tensordict.get(key)
    N = reference_tensor.shape[0]

    cat_data = torch.cat([reference_tensor, target_tensor], dim=0)
    _, unique_indices = torch.unique(cat_data, dim=0, sorted=True, return_inverse=True)

    common_indices = torch.isin(unique_indices[N:], unique_indices[:N])
    filtered_target_tensordict = target_tensordict[~common_indices]

    return filtered_target_tensordict


def smiles_to_tensordict(
    smiles: torch.Tensor,
    reward: torch.Tensor,
    device: str | torch.device = "cpu",
):
    """Create an episode Tensordict from a batch of SMILES."""
    B, T = smiles.shape
    mask = smiles != -1
    rewards = torch.zeros(B, T, 1)
    rewards[:, -1] = reward
    done = torch.zeros(B, T, 1, dtype=torch.bool)
    done[:, -1] = True

    smiles_tensordict = TensorDict(
        {
            "observation": smiles[:, :-1].int(),
            "action": smiles[:, 1:],
            "done": done[:, :-1],
            "terminated": done[:, :-1],
            "mask": mask[:, :-1],
            "next": TensorDict(
                {
                    "observation": smiles[:, 1:].int(),
                    "reward": rewards[:, 1:],
                    "done": done[:, 1:],
                    "terminated": done[:, 1:],
                },
                batch_size=[B, T - 1],
            ),
        },
        batch_size=[B, T - 1],
    )

    smiles_tensordict = smiles_tensordict.to(device)

    return smiles_tensordict


from __future__ import annotations

import warnings
from typing import Callable, Sequence

import torch

from acegen.vocabulary.base import Vocabulary
from tensordict import TensorDictBase
from tensordict.utils import NestedKey
from torchrl.envs.transforms.transforms import Transform


class SMILESReward(Transform):
    """Transform to add a reward to a SMILES.

    This class requires either a reward_function or a reward_function_creator. If both are provided,
    the reward_function will be used. If neither are provided, a ValueError will be raised.

    Args:
        vocabulary (Vocabulary): A vocabulary object with at least encode and decode methods.
        reward_function (callable, optional): A callable that takes a list of SMILES and returns
        a list of rewards.
        reward_function_creator (callable, optional): A callable that creates a reward function.
        in_keys (sequence of NestedKey, optional): keys to be updated.
            default: ["observation", "reward"]
        out_keys (sequence of NestedKey, optional): destination keys.
            Defaults to ``in_keys``.
        reward_scale (int, optional): The scale to apply to the reward.
    """

    def __init__(
        self,
        vocabulary: Vocabulary,
        reward_function: Callable = None,
        reward_function_creator: Callable = None,
        in_keys: Sequence[NestedKey] | None = None,
        out_keys: Sequence[NestedKey] | None = None,
        reward_scale=1.0,
    ):

        if reward_function is None and reward_function_creator is None:
            raise ValueError(
                "Either reward_function or reward_function_creator must be provided."
            )

        if not reward_function:
            if not isinstance(reward_function_creator, Callable):
                raise ValueError(
                    "A reward_function_creator was provided but it must be a callable"
                    "that returns a reward function, not a {}".format(
                        type(reward_function_creator)
                    )
                )
            reward_function = reward_function_creator()

        if not isinstance(reward_function, Callable):
            raise ValueError(
                "A reward_function was provided but it must be a callable, not a {}".format(
                    type(reward_function)
                )
            )

        if out_keys is None:
            out_keys = ["reward"]
        if in_keys is None:
            in_keys = ["SMILES"]
        self.reward_scale = reward_scale

        super().__init__(in_keys, out_keys)

        self.vocabulary = vocabulary
        self.reward_function = reward_function

    def forward(self, tensordict: TensorDictBase) -> TensorDictBase:
        self._call(tensordict.get("next"))
        return tensordict

    def _call(self, tensordict: TensorDictBase, _reset=None) -> TensorDictBase:

        # Get steps where trajectories end
        device = tensordict.device
        done = tensordict.get("done").squeeze(-1)

        sub_tensordict = tensordict.get_sub_tensordict(done)

        if len(sub_tensordict) == 0:
            return tensordict

        # Get reward and smiles
        reward = sub_tensordict.get(self.out_keys[0])
        smiles = sub_tensordict.get(self.in_keys[0])

        # Get smiles as strings
        smiles_list = []
        for smi in smiles:
            smiles_list.append(
                self.vocabulary.decode(smi.cpu().numpy(), ignore_indices=[-1])
            )

        # Calculate reward - try multiple times in case of RuntimeError
        max_attempts = 3
        for i in range(max_attempts):
            try:
                _reward = torch.tensor(self.reward_function(smiles_list), device=device)
                reward += _reward.reshape(reward.shape)
                break
            except RuntimeError:
                if i == max_attempts - 1:
                    raise
                else:
                    warnings.warn(
                        "RuntimeError in reward function. Trying again. Attempt {}/{}".format(
                            i + 1, max_attempts
                        )
                    )
                    continue

        sub_tensordict.set(self.out_keys[0], reward * self.reward_scale, inplace=True)

        return tensordict
