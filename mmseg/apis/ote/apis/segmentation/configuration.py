# Copyright (C) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

from attr import attrs
from sys import maxsize

from ote_sdk.configuration.elements import (ParameterGroup,
                                            add_parameter_group,
                                            boolean_attribute,
                                            configurable_float,
                                            configurable_integer,
                                            selectable,
                                            string_attribute,
                                            ModelConfig)
from ote_sdk.configuration.model_lifecycle import ModelLifecycle

from .configuration_enums import POTQuantizationPreset


@attrs
class OTESegmentationConfig(ModelConfig):
    header = string_attribute("Configuration for an semantic segmentation task")
    description = header

    @attrs
    class __LearningParameters(ParameterGroup):
        header = string_attribute("Learning Parameters")
        description = header

        batch_size = configurable_integer(
            default_value=8,
            min_value=1,
            max_value=64,
            header="Batch size",
            description="The number of training samples seen in each iteration of training. Increasing this value "
            "improves training time and may make the training more stable. A larger batch size has higher "
            "memory requirements.",
            warning="Increasing this value may cause the system to use more memory than available, "
            "potentially causing out of memory errors, please update with caution.",
            affects_outcome_of=ModelLifecycle.TRAINING
        )

        num_iters = configurable_integer(
            default_value=1,
            min_value=1,
            max_value=100000,
            header="Number of training iterations",
            description="Increasing this value causes the results to be more robust but training time will be longer.",
            affects_outcome_of=ModelLifecycle.TRAINING
        )

        learning_rate = configurable_float(
            default_value=1e-3,
            min_value=1e-05,
            max_value=1e-01,
            header="Learning rate",
            description="Increasing this value will speed up training convergence but might make it unstable.",
            affects_outcome_of=ModelLifecycle.TRAINING
        )

        learning_rate_fixed_iters = configurable_integer(
            default_value=100,
            min_value=0,
            max_value=5000,
            header="Number of iterations for fixed learning rate",
            description="",
            affects_outcome_of=ModelLifecycle.TRAINING
        )

        learning_rate_warmup_iters = configurable_integer(
            default_value=100,
            min_value=0,
            max_value=5000,
            header="Number of iterations for learning rate warmup",
            description="",
            affects_outcome_of=ModelLifecycle.TRAINING
        )

        num_workers = configurable_integer(
            default_value=0,
            min_value=0,
            max_value=8,
            header="Number of cpu threads to use during batch generation",
            description="Increasing this value might improve training speed however it might cause out of memory "
                        "errors. If the number of workers is set to zero, data loading will happen in the main "
                        "training thread.",
            affects_outcome_of=ModelLifecycle.NONE
        )

        num_checkpoints = configurable_integer(
            default_value=5,
            min_value=1,
            max_value=100,
            header="Number of checkpoints that is done during the single training round",
            description="",
            affects_outcome_of=ModelLifecycle.NONE
        )

    @attrs
    class __Postprocessing(ParameterGroup):
        header = string_attribute("Postprocessing")
        description = header

        blur_strength = configurable_integer(
            header="Blur strength",
            description="With a higher value, the segmentation output will be smoother, but less accurate.",
            default_value=1,
            min_value=1,
            max_value=25,
            affects_outcome_of=ModelLifecycle.INFERENCE
        )

        soft_threshold = configurable_float(
            default_value=0.5,
            header="Soft threshold",
            description="The threshold to apply to the probability output of the model, for each pixel. A higher value "
                        "means a stricter segmentation prediction.",
            min_value=0.0,
            max_value=1.0,
            affects_outcome_of=ModelLifecycle.INFERENCE
        )

    @attrs
    class __AlgoBackend(ParameterGroup):
        header = string_attribute("Internal Algo Backend parameters")
        description = header
        visible_in_ui = boolean_attribute(False)

        template = string_attribute("template.yaml")
        model = string_attribute("model.py")
        model_name = string_attribute("semantic segmentation model")
        data_pipeline = string_attribute("data_pipeline.py")

    @attrs
    class __POTParameter(ParameterGroup):
        header = string_attribute("POT Parameters")
        description = header

        stat_subset_size = configurable_integer(
            header="Number of data samples",
            description="Number of data samples used for post-training optimization",
            default_value=300,
            min_value=1,
            max_value=maxsize
        )

        preset = selectable(default_value=POTQuantizationPreset.PERFORMANCE,
                            header="Preset",
                            description="Quantization preset that defines quantization scheme",
                            editable=False,
                            visible_in_ui=False)

    learning_parameters = add_parameter_group(__LearningParameters)
    algo_backend = add_parameter_group(__AlgoBackend)
    postprocessing = add_parameter_group(__Postprocessing)
    pot_parameters = add_parameter_group(__POTParameter)