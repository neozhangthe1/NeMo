# -*- coding: utf-8 -*-

# =============================================================================
# Copyright (c) 2020 NVIDIA. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

import collections
# from collections import OrderedDict
from typing import Dict, Optional

import nemo
from nemo.core.neural_factory import NeuralType, OperationMode
from nemo.core.neural_interface import NeuralInterface
from nemo.core.neural_types import (
    CanNotInferResultNeuralType,
    NeuralPortNameMismatchError,
    NeuralPortNmTensorMismatchError,
    NeuralType,
    NeuralTypeComparisonResult,
    NmTensor,
)


class NeuralGraph(NeuralInterface):
    def __init__(self, operation_mode, name=None):
        """
            Constructor. Initializes graph variables.

            Args:
                operation_mode: Graph operation mode, that will be propagated along modules during graph creation.
                [training | eval]
                name: Name of the graph (optional)
        """
        # Call integrace constructor.
        super().__init__()
        print('__init__ called')
        # Store name and operation mode.
        self._operation_mode = operation_mode
        if name is None:
            # Simply take the name of operation.
            self._name = str(self._operation_mode)[14:]
        else:
            self._name = name
        # Input and output ports - empty for now.
        self._binded_input_ports = {}
        self._binded_output_ports = {}
        self._binded_input_tensors = {}
        self._binded_output_tensors = {}
        # Operations.
        self._operation_list = []
        # Register graph.
        self._app_state.register_graph(self)
        print("Created graph: ", self._name)

    def __call__(self, **kwargs):
        """
            This method "inserts" one existing neural graph into another one.
            Also checks if all inputs were provided and properly connects them.

        """
        print(" Neural Graph:__call__")
        # Get input and output ports definitions.
        input_port_defs = self.input_ports
        output_port_defs = self.output_ports

        # TODO: check graph operation mode compatibility.

        # "Copy" all the operations from the previous graph.
        for operation in self._operation_list:
            self._app_state.active_graph.record_operation(*operation)

        # print(self._operation_list)

        # Iterate through all passed parameters.
        for port_name, port_content in kwargs.items():
            # make sure that passed arguments correspond to input port names
            if port_name not in input_port_defs.keys():
                raise NeuralPortNameMismatchError("Wrong input port name: {0}".format(port_name))

            # Check what was actually passed.
            if isinstance(port_content, nemo.core.NeuralGraph):

                # TODO: make sure that port_content ==  self._app_state.active_graph ?!?!

                # Bind this input port to a neural graph.
                port_content.bind_input(port_name, input_port_defs[port_name], self)

                # It is "compatible by definition";), so we don't have to check this port further.

            else:  # : port_content is a neural module.
                # Compare input port definition with the received definition.
                input_port = input_port_defs[port_name]
                type_comatibility = input_port.compare(port_content)
                if (
                    type_comatibility != NeuralTypeComparisonResult.SAME
                    and type_comatibility != NeuralTypeComparisonResult.GREATER
                ):
                    raise NeuralPortNmTensorMismatchError(
                        "\n\nIn {0}. \n"
                        "Port: {1} and a NmTensor it was fed are \n"
                        "of incompatible neural types:\n\n{2} \n\n and \n\n{3}"
                        "\n\nType comparison result: {4}".format(
                            self.__class__.__name__,
                            port_name,
                            input_port_defs[port_name],
                            port_content,
                            type_comatibility,
                        )
                    )
        # TODO CHECK 1: Are we making sure that ALL necessary inputs that were PASSED?

        # Here we will store the results.
        results = None

        # This part is different. Now the goal is not to create NEW "tensors", but to return the BINDED ones!
        if len(output_port_defs) == 1:
            out_name = list(output_port_defs)[0]
            # out_type = output_port_defs[out_name]
            # TODO CHECK 2: Why are we returning "something" (having input type) if there SHOULD be NO output?
            results = self._binded_output_ports[out_name]

            # Bind the output ports.
            print("Neural graph LEN 1 -> going to bind_outputs")
            self._app_state.active_graph.bind_outputs(output_port_defs, [results])

        else:
            result = []
            # for out_port, n_type in output_port_defs.items():
            #    out_type = n_type
            #    result.append(NmTensor(producer=self, producer_args=kwargs, name=out_port, ntype=out_type,))
            for name, tensor in self._binded_output_tensors.items():
                result.append(tensor)

            # Creating ad-hoc class for returning from module's forward pass.
            output_class_name = f'{self.__class__.__name__}Output'
            field_names = list(output_port_defs)
            result_type = collections.namedtuple(typename=output_class_name, field_names=field_names,)

            print("Neural graph LEN MORE -> going to bind_outputs")
            # Bind the output ports.
            self._app_state.active_graph.bind_outputs(output_port_defs, result)

            # Tie tuple of output tensors with corresponding names.
            results = result_type(*result)

        # Return the results.
        return results

    @property
    def input_ports(self) -> Optional[Dict[str, NeuralType]]:
        """Returns definitions of module input ports.

        Returns:
          A (dict) of module's input ports names to NeuralTypes mapping
        """
        return self._binded_input_ports

    @property
    def output_ports(self) -> Optional[Dict[str, NeuralType]]:
        """Returns definitions of module output ports

        Returns:
          A (dict) of module's output ports names to NeuralTypes mapping
        """
        return self._binded_output_ports

    def __enter__(self):
        """ Activates given graph as current. """
        print("Entering graph: ", self._name)
        self._app_state.active_graph = self
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """ Deactivates current graph. """
        print("Exiting graph: ", self._name)
        self._app_state.active_graph = None
        if exc_type:
            print(f'exc_type: {exc_type}')
            print(f'exc_value: {exc_value}')
            print(f'exc_traceback: {exc_traceback}')

    def __str__(self):
        """ Prints a nice summary. """
        # TODO: a nice summary. ;)
        desc = "`{}` ({}):\n".format(self._name, len(self._operation_list))
        for op in self._operation_list:
            desc = desc + "  {}\n".format(type(op[0]).__name__)
        return desc

    def record_operation(self, module, inputs):
        """
            Records the operation (module plus passed inputs) on a list.
        """
        self._operation_list.append([module, inputs])

    def bind_input(
        self, port_name, port_definition,
    ):
        print("Binding input: `{}`: def = `{}` value = NONE".format(port_name, port_definition))
        # Copy the definition of the port to graph input port definition.
        self._binded_input_ports[port_name] = port_definition

        # Indicate that this tensor is missing and has to be provided!
        self._binded_input_tensors[port_name] = None
        print("Binding input DONE!")
        # Remember that it leads to a given module!

    def bind_outputs(self, output_port_defs, output_values):
        # print("Binding ALL outputs: defs = `{}`, values = `{}`".format(output_port_defs, output_values))

        for (output_name, output_definition), output_value in zip(output_port_defs.items(), output_values):
            # print(
            #    "Binding output: key = `{}`: def = `{}`, value = `{}`".format(
            #        output_name, type(output_definition), type(output_value)
            #    )
            # )
            # Copy the definition of the port to graph input port definition.
            self._binded_output_ports[output_name] = output_definition

            # Bind output tensors.

            self._binded_output_tensors[output_name] = output_value

    def show_binded_inputs(self):
        print("Binded input ports: ")
        for key, value in self._binded_input_ports.items():
            print(" * `{}`: `{}` ({})".format(key, value, type(value)))

        print("Binded input tensors: ")
        for key, value in self._binded_input_tensors.items():
            print(" * `{}`: `{}` ({})".format(key, value, type(value)))

    def show_binded_outputs(self):
        print("Binded output ports: ")
        for key, value in self._binded_output_ports.items():
            print(" * `{}`: `{}` ({})".format(key, value, type(value)))

        print("Binded output tensors: ")
        for key, value in self._binded_output_tensors.items():
            print(" * `{}`: `{}` ({})".format(key, value, type(value)))