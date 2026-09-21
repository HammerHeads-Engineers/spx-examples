# SPDX-License-Identifier: MIT
# Minimal implementation of a custom action that simulates intermittent
# contact faults on a PT100-like sensor. It randomly injects either a
# drop-to-zero or a spike to a configured value. Typical usage maps this
# action to an *external* attribute target so core simulation logic
# remains stable while the presented value exhibits faults.

import random
from spx_sdk.actions import Action
from spx_sdk.registry import register_class


@register_class(name="contact_fault")
class ContactFault(Action):
    """Randomly injects spikes/drops into the target signal.

    Parameters (populated from YAML):
      - probability (float): chance to inject a fault on each run() step. Default: 0.01
      - spike_value (float): value to use for spike events. Default: 1000.0
      - drop_ratio (float): probability of choosing a drop-to-zero vs. spike. Default: 0.5
      - seed (int|None): optional RNG seed for reproducibility. Default: None
    """

    def _populate(self, definition):
        # Sensible defaults for quick onboarding
        self.probability = 0.01
        self.spike_value = 1000.0
        self.drop_ratio = 0.5
        self.seed = None
        print("Populating ContactFault from definition:", definition)
        # Allow parent class to override from definition (if provided)
        super()._populate(definition)

    def prepare(self):
        # Reset any internal state and seed RNG if requested
        print("Preparing ContactFault with seed:", self.seed)
        super().prepare()
        random.seed(self.seed)

    def run(self):
        """Possibly corrupt each mapped output according to probability.
        Returns True if at least one fault was injected in this step.
        """
        faulted = False
        for output in self.outputs.values():
            # Decide if a fault happens on this step
            if random.random() < float(self.probability):
                # Choose between drop-to-zero and spike
                if random.random() < float(self.drop_ratio):
                    output.set(0.0)
                else:
                    output.set(float(self.spike_value))
                faulted = True
        return faulted
