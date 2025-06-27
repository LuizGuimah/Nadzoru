from jinja2 import Environment, FileSystemLoader, meta
import math



class BaseGenerator():
    template_path = 'codegen/templates'
    def __init__(self, *args, **kwargs):
        self.options = dict()
        self.device = None
        loader = FileSystemLoader(self.template_path)
        self.environment = Environment(loader=loader)

    def show(self):
        devs = ''
        opts = ''
        for k, v in self.items():
            devs += f'{k}, '
            opts += f'{k}: {v}\n\t'

        return f'{__class__}\nDevice: {devs}\nOptions: {opts}'

    def set_device(self, device):
        self.options = dict()
        self.device = device
    
    def get_options(self):
        return self.options.items()

    def set_option(self, opt_name, label, widget_type, opt):
        self.options[opt_name] = opt
        self.options[opt_name].update({'label': label, 'widget_type': widget_type})

    def set_template_path(self, template_path):
        self.template_path = template_path

    def _write(self, output_path=None, arguments:dict={}):
        for tmplt_name in self.templates_name:
            
            if output_path is None:
                out_path = f'codegen/output/{tmplt_name}'
            else:
                out_path = f'{output_path}/{tmplt_name}'
            
            tmplt_vars = self.get_template_variables(tmplt_name)
            vars_to_render = {key: arguments[key] for key in arguments.keys() & tmplt_vars}
            vars_to_render['generator'] = self

            template = self.environment.get_template(tmplt_name)
            render = template.render(**vars_to_render)
            with open(out_path, 'w') as out_file:
                out_file.write(render)

    def get_template_variables(self, filename):
        template_source = self.environment.loader.get_source(self.environment, filename)
        parsed_content = self.environment.parse(template_source)
        return meta.find_undeclared_variables(parsed_content)
    
class GenericMcu(BaseGenerator):
    templates_name = ['generic_mic.h']
    template_path = 'codegen/templates'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_template_path(self.template_path)

    def generate_sup(self, automaton_list):
        '''This will generate the information contained in a supervisor.
        
        [data]      : [n of out transitions in a state, 'event_name1', from_state, to_state, 'event_name2', from_state, to_state]...

        {data_pos}  : {automaton0: index, automaton1, index, ...} - contains the initial index for each automaton in [data]

        {state_map} : {state: number}, where number is an arbitrary value that will represent the state

        {events,}   : set of all events. Events with the same name in different automatons are treated as the same event

        [event_map] : [[automaton0], [automaton1], ...] where [automaton0] is a list of booleans with n_events elements. If True, the automaton contains the event in this index (related to the {event, } set)
        
        '''
        data_pos = dict()
        state_map = dict()
        data = list()
        event_map = list()
        events = set()
        initial_state = list()

        for k_automaton, automaton in enumerate(automaton_list):
            # automatons[k_automaton] = automaton
            data_pos[k_automaton] = len(data)
            for k_state, state in enumerate(automaton.states):
                state_map[state] = k_state
                if state == automaton.initial_state:
                    initial_state.append(k_state)
            for k_state, state in enumerate(automaton.states):
                data.append(len(state.out_transitions))
                for k_transition, transition in enumerate(state.out_transitions):
                    # treats events with identical names as the same event
                    if transition.event.name not in [ev.name for ev in events]:
                        events.add(transition.event)
                    data.append(f'EV_{transition.event.name}')
                    data.append(math.floor(state_map[transition.to_state]/256))
                    data.append(state_map[transition.to_state] % 256)

        for automaton in automaton_list:
            event_map.append([True if event.name in [ev.name for ev in automaton.events] else False for event in events])

        return (data, data_pos, state_map, events, event_map, initial_state)

class ArduinoGenerator(GenericMcu):
    templates_name = ['arduino.ino', 'arduino.h']
    template_path = 'codegen/templates'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('arduino')

        self.set_template_path(self.template_path) 
        self.RANDOM_PSEUDOFIX = 0
        self.RANDOM_PSEUDOAD = 1
        self.RANDOM_AD = 2
        self.RANDOM_PSEUDOTIME = 3
        self.INPUT_TIMER = 0
        self.INPUT_MULTIPLEXED = 1
        self.INPUT_RS232 = 2


        self.set_option('random_fn', "Random Type", 'choice', {
            'options': [
                ("Pseudo Random Seed Fixed",        self.RANDOM_PSEUDOFIX),
                ("Pseudo Random Seed by AD input",  self.RANDOM_PSEUDOAD),
                ("AD input",                        self.RANDOM_AD),
                ("Pseudo Random Seed by Time",      self.RANDOM_PSEUDOTIME)
            ]})
        self.set_option('ad_port', "AD Port", 'choice', {
            'options': [
                ("A0", 'A0'), ("A1", 'A1'), ("A2", 'A2'),
                ("A4", 'A4'), ("A5", 'A5')
                       ]
        })
        self.set_option('input_fn', "Input (Delay Sensitibility)", 'choice', {
            'options': [
                ("Timer Interruption",                  self.INPUT_TIMER),
                ("Multiplexed External Interruption",   self.INPUT_MULTIPLEXED)#,
                #("RS232 with Interrupt",                self.INPUT_RS232)
                       ]     
        })

    def write(self, automatons, vars_dict, output_path):
        output_dict = self.generate_strings(automatons)
        output_dict.update(vars_dict)
        self._write(output_path, output_dict)

    @staticmethod
    def _gen_str(data_to_gen):
        aux = list()
        if type(data_to_gen) == dict:
            for v in data_to_gen.values():
                aux.append(str(v))
        elif type(data_to_gen) == list:
            for element in data_to_gen:
                aux.append(str(element))
        res = ', '.join(aux)
        res = res.replace("[", "{")
        res = res.replace("]", "}")
        res = f'{{{res}}}'
        return res

    def add_extra_properties(self, events): # By default, do nothing. Overwrite this function in the extensions to add more properties.
        return dict()

    def generate_strings(self, automatons):
        data, data_pos, state_map, events, event_map, initial_state = self.generate_sup(automatons)

        sup_data_pos = self._gen_str(data_pos)
        sup_data = self._gen_str(data)
        sup_init_state = self._gen_str(initial_state)
        sup_current_state = sup_init_state

        str_controllable = ['1' if event.controllable else '0'  for event in events]
        ev_controllable = self._gen_str(str_controllable)

        ev_extra_properties = dict()
        ev_extra_properties.update(self.add_extra_properties(events))

        str_event_map = list()
        for automaton_event_list in event_map:
            str_event_map.append([1 if event else 0 for event in automaton_event_list])
        sup_event_map = self._gen_str(str_event_map)
        result = {'automaton_list': automatons,
                  'events': events,
                  'data': data,
                  'ev_controllable': ev_controllable,
                  'sup_init_state': sup_init_state,
                  'sup_current_state': sup_current_state,
                  'sup_data_pos': sup_data_pos,
                  'sup_data': sup_data,
                  'sup_event_map': sup_event_map}
        
        # Loop ev_extra_properties and add to result
        for k, v in ev_extra_properties.items():
            result[k] = v
        return result

class KilobotGenerator(GenericMcu):
    templates_name = ['kilobotAtmega328.c']
    template_path = 'codegen/templates'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('kilobot')
        self.set_template_path(self.template_path) 

    def write(self, automatons, vars_dict, output_path):
        output_dict = self.generate_strings(automatons)
        output_dict.update(vars_dict)
        self._write(output_path, output_dict)

    @staticmethod
    def _gen_str(data_to_gen):
        aux = list()
        if type(data_to_gen) == dict:
            for v in data_to_gen.values():
                aux.append(str(v))
        elif type(data_to_gen) == list:
            for element in data_to_gen:
                aux.append(str(element))
        res = ', '.join(aux)
        res = res.replace("[", "{")
        res = res.replace("]", "}")
        res = f'{{{res}}}'
        return res

    def add_extra_properties(self, events): # By default, do nothing. Overwrite this function in the extensions to add more properties.
        return dict()

    def generate_strings(self, automatons):
        data, data_pos, state_map, events, event_map, initial_state = self.generate_sup(automatons)

        sup_data_pos = self._gen_str(data_pos)
        sup_data = self._gen_str(data)
        sup_init_state = self._gen_str(initial_state)
        sup_current_state = sup_init_state

        str_controllable = ['1' if event.controllable else '0'  for event in events]
        ev_controllable = self._gen_str(str_controllable)

        ev_extra_properties = dict()
        ev_extra_properties.update(self.add_extra_properties(events))

        str_event_map = list()
        for automaton_event_list in event_map:
            str_event_map.append([1 if event else 0 for event in automaton_event_list])
        sup_event_map = self._gen_str(str_event_map)
        result = {'automaton_list': automatons,
                  'events': events,
                  'data': data,
                  'ev_controllable': ev_controllable,
                  'sup_init_state': sup_init_state,
                  'sup_current_state': sup_current_state,
                  'sup_data_pos': sup_data_pos,
                  'sup_data': sup_data,
                  'sup_event_map': sup_event_map}
        
        # Loop ev_extra_properties and add to result
        for k, v in ev_extra_properties.items():
            result[k] = v
        return result

class CGenerator(GenericMcu):
    templates_name = ['generic_mic.c', 'generic_mic.h']
    template_path = 'codegen/templates'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('C')
        self.set_template_path(self.template_path) 

    def write(self, automatons, vars_dict, output_path):
        output_dict = self.generate_strings(automatons)
        output_dict.update(vars_dict)
        self._write(output_path, output_dict)

    @staticmethod
    def _gen_str(data_to_gen):
        aux = list()
        if type(data_to_gen) == dict:
            for v in data_to_gen.values():
                aux.append(str(v))
        elif type(data_to_gen) == list:
            for element in data_to_gen:
                aux.append(str(element))
        res = ', '.join(aux)
        res = res.replace("[", "{")
        res = res.replace("]", "}")
        res = f'{{{res}}}'
        return res

    def add_extra_properties(self, events): # By default, do nothing. Overwrite this function in the extensions to add more properties.
        return dict()

    def generate_strings(self, automatons):
        data, data_pos, state_map, events, event_map, initial_state = self.generate_sup(automatons)

        sup_data_pos = self._gen_str(data_pos)
        sup_data = self._gen_str(data)
        sup_init_state = self._gen_str(initial_state)
        sup_current_state = sup_init_state

        str_controllable = ['1' if event.controllable else '0'  for event in events]
        ev_controllable = self._gen_str(str_controllable)

        ev_extra_properties = dict()
        ev_extra_properties.update(self.add_extra_properties(events))

        str_event_map = list()
        for automaton_event_list in event_map:
            str_event_map.append([1 if event else 0 for event in automaton_event_list])
        sup_event_map = self._gen_str(str_event_map)
        result = {'automaton_list': automatons,
                  'events': events,
                  'data': data,
                  'ev_controllable': ev_controllable,
                  'sup_init_state': sup_init_state,
                  'sup_current_state': sup_current_state,
                  'sup_data_pos': sup_data_pos,
                  'sup_data': sup_data,
                  'sup_event_map': sup_event_map}
        
        # Loop ev_extra_properties and add to result
        for k, v in ev_extra_properties.items():
            result[k] = v
        return result

class CPPGenerator(GenericMcu):
    templates_name = ['supervisor.yaml', 'sct.cpp', 'sct.h']
    template_path = 'codegen/templates'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('C')
        self.set_template_path(self.template_path) 

    def write(self, automatons, vars_dict, output_path):
        output_dict = self.generate_strings(automatons)
        output_dict.update(vars_dict)
        self._write(output_path, output_dict)

    @staticmethod
    def _gen_str(data_to_gen):
        aux = list()
        if type(data_to_gen) == dict:
            for v in data_to_gen.values():
                aux.append(str(v))
        elif type(data_to_gen) == list:
            for element in data_to_gen:
                aux.append(str(element))
        res = ', '.join(aux)
        # res = res.replace("[", "{")
        # res = res.replace("]", "}")
        # res = f'{{{res}}}'
        return res

    def add_extra_properties(self, events): # By default, do nothing. Overwrite this function in the extensions to add more properties.
        return dict()

    def generate_strings(self, automatons):
        data, data_pos, state_map, events, event_map, initial_state = self.generate_sup(automatons)

        sup_data_pos = self._gen_str(data_pos)
        sup_data = self._gen_str(data)
        sup_init_state = self._gen_str(initial_state)
        sup_current_state = sup_init_state

        str_controllable = ['1' if event.controllable else '0'  for event in events]
        ev_controllable = self._gen_str(str_controllable)

        ev_extra_properties = dict()
        ev_extra_properties.update(self.add_extra_properties(events))

        str_event_map = list()
        for automaton_event_list in event_map:
            str_event_map.append([1 if event else 0 for event in automaton_event_list])
        sup_event_map = self._gen_str(str_event_map)

        str_event_names = [f'EV_{event.name}' for event in events]
        event_names = self._gen_str(str_event_names)

        result = {'automaton_list': automatons,
                  'events': events,
                  'event_names': event_names,
                  'data': data,
                  'ev_controllable': ev_controllable,
                  'sup_init_state': sup_init_state,
                  'sup_current_state': sup_current_state,
                  'sup_data_pos': sup_data_pos,
                  'sup_data': sup_data,
                  'sup_event_map': sup_event_map}
        
        # Loop ev_extra_properties and add to result
        for k, v in ev_extra_properties.items():
            result[k] = v
        return result

class PythonGenerator(GenericMcu):
    templates_name = ['supervisor.yaml', 'sct.py']
    template_path = 'codegen/templates'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('Python')
        self.set_template_path(self.template_path) 

    def generate_sup(self, automaton_list):
        '''This will generate the information contained in a supervisor.
        
        [data]      : [n of out transitions in a state, 'event_name1', from_state, to_state, 'event_name2', from_state, to_state]...

        {data_pos}  : {automaton0: index, automaton1, index, ...} - contains the initial index for each automaton in [data]

        {state_map} : {state: number}, where number is an arbitrary value that will represent the state

        {events,}   : set of all events. Events with the same name in different automatons are treated as the same event

        [event_map] : [[automaton0], [automaton1], ...] where [automaton0] is a list of booleans with n_events elements. If True, the automaton contains the event in this index (related to the {event, } set)
        
        '''
        data_pos = dict()
        state_map = dict()
        data = list()
        event_map = list()
        events = set()
        initial_state = list()

        for k_automaton, automaton in enumerate(automaton_list):
            # automatons[k_automaton] = automaton
            data_pos[k_automaton] = len(data)
            for k_state, state in enumerate(automaton.states):
                state_map[state] = k_state
                if state == automaton.initial_state:
                    initial_state.append(k_state)
            for k_state, state in enumerate(automaton.states):
                data.append(len(state.out_transitions))
                for k_transition, transition in enumerate(state.out_transitions):
                    # treats events with identical names as the same event
                    if transition.event.name not in [ev.name for ev in events]:
                        events.add(transition.event)
                    data.append(f'EV_{transition.event.name}')
                    data.append(math.floor(state_map[transition.to_state]/256))
                    data.append(state_map[transition.to_state] % 256)

        for automaton in automaton_list:
            event_map.append([True if event.name in [ev.name for ev in automaton.events] else False for event in events])

        return (data, data_pos, state_map, events, event_map, initial_state)

    def write(self, automatons, vars_dict, output_path):
        output_dict = self.generate_strings(automatons)
        output_dict.update(vars_dict)
        self._write(output_path, output_dict)

    @staticmethod
    def _gen_str(data_to_gen):
        aux = list()
        if type(data_to_gen) == dict:
            for v in data_to_gen.values():
                aux.append(str(v))
        elif type(data_to_gen) == list:
            for element in data_to_gen:
                aux.append(str(element))
        res = ', '.join(aux)
        # res = res.replace("[", "{")
        # res = res.replace("]", "}")
        # res = f'{{{res}}}'
        return res

    def add_extra_properties(self, events): # By default, do nothing. Overwrite this function in the extensions to add more properties.
        return dict()

    def generate_strings(self, automatons):
        data, data_pos, state_map, events, event_map, initial_state = self.generate_sup(automatons)

        sup_data_pos = self._gen_str(data_pos)
        sup_data = self._gen_str(data)
        sup_init_state = self._gen_str(initial_state)
        sup_current_state = sup_init_state

        str_controllable = ['1' if event.controllable else '0'  for event in events]
        ev_controllable = self._gen_str(str_controllable)

        ev_extra_properties = dict()
        ev_extra_properties.update(self.add_extra_properties(events))

        str_event_map = list()
        for automaton_event_list in event_map:
            str_event_map.append([1 if event else 0 for event in automaton_event_list])
        sup_event_map = self._gen_str(str_event_map)

        str_event_names = [f'EV_{event.name}' for event in events]
        event_names = self._gen_str(str_event_names)

        result = {'automaton_list': automatons,
                  'events': events,
                  'event_names': event_names,
                  'data': data,
                  'ev_controllable': ev_controllable,
                  'sup_init_state': sup_init_state,
                  'sup_current_state': sup_current_state,
                  'sup_data_pos': sup_data_pos,
                  'sup_data': sup_data,
                  'sup_event_map': sup_event_map}
        
        # Loop ev_extra_properties and add to result
        for k, v in ev_extra_properties.items():
            result[k] = v
        return result
    
class IEC61499Generator(GenericMcu):
    template_name = 'generic_iec61499.fbt'
    template_path = 'codegen/templates/'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('IEC61499')
        self.set_template_path(self.template_path)

    #override
    def _write(self, output_path=None, arguments:dict={}):
        if output_path is None:
            out_path = f'codegen/output/{arguments['fb_name'] + ".fbt"}'
        else:
            out_path = output_path + '/' + arguments['fb_name'] + ".fbt"
        
        tmplt_vars = self.get_template_variables(self.template_name)
        vars_to_render = {key: arguments[key] for key in arguments.keys() & tmplt_vars}
        vars_to_render['generator'] = self

        template = self.environment.get_template(self.template_name)
        render = template.render(**vars_to_render)
        with open(out_path, 'w') as out_file:
            out_file.write(render)

    def write(self, automata_list, vars_dict, output_path):          
        #{event.name : {su_name: "SUx", enabled_states : [Sx, Sy...], ms_list : ["MSx", "MSy"...]}}
        eg_dict = dict()

        for automato in automata_list:
            if automato._name[:2] == "SU":
                fb_name = automato._name[:-4]
                output_dict = self.generate_su(automato, fb_name, eg_dict)
                output_dict.update(vars_dict)
                self._write(output_path, output_dict)
            
        for automato in automata_list:
            if automato._name[:2] == "MS":
                fb_name = automato._name[:-4]
                output_dict = self.generate_ms(automato, fb_name, eg_dict)
                output_dict.update(vars_dict)
                self._write(output_path, output_dict)

    
        if eg_dict:
            for event_name in eg_dict:
                #print(event_name + " " + str(eg_dict[event_name]))
                output_dict = self.generate_eg(event=event_name, eg_info=eg_dict[event_name])
                output_dict.update(vars_dict)
                self._write(output_path, output_dict)

    
    def generate_su(self, automato, fb_name, eg_dict):
    # Inicializa listas para eventos e variáveis
        initial_state = automato.initial_state.name
        start_name = "S" + initial_state + "_Start"

        # {nome : [related_vars]}
        event_inputs = {"Start" : []}
        event_outputs = {"StartO" : ["State"], "Out" : ["State"]}
        input_vars = None
        output_vars = [{"name": "State", "type": "INT"}]
        states = [{"name" : "START", "comment" : "Initial State"}]
        transitions = [{"source" : "START", "destination" : start_name, "condition" : "Start"}]
        algorithms = []

        initial_state = automato.initial_state

        # Preenche eventos de entrada e saída
        for event in automato.event_name_map().values():
            event_inputs[event.name] = None
            event_outputs["Out_" + event.name] = ["State"]

        # Transições a partir do estado inicial
        for transition in initial_state.out_transitions:
            transitions.append({
                "source": start_name,
                "destination": "S" + transition.to_state.name,
                "condition": transition.event
            })
        states.append({
            "name": start_name,
            "alg": "ALG0",
            "output": ["StartO", "Out"]
        })  

        for state in automato.states:
            state_name = state.name
            # Mapeia os eventos de entrada para o estado
            event_map = {}
            for transition in state.in_transitions:
                event = transition.event
                if event.controllable:
                    if eg_dict.get(event.name):
                        eg_dict[event.name]["enabled_states"].append(transition.from_state)
                    else:
                        eg_info = {
                            "su_name" : fb_name,
                            "enabled_states" : [transition.from_state.name],
                            "ms_list" : []
                        }
                        eg_dict[event.name] = eg_info


                if event not in event_map:
                    event_map[event] = []
                event_map[event].append(transition.from_state)

            # Se só há um evento de entrada, adiciona transição direta
            if len(event_map) == 1:
                event = next(iter(event_map))
                #adiciona o estado a lista de estados
                alg_name = "ALG"+state_name
                out_name = "Out_" + event.name
                states.append({
                "name": "S"+state_name,
                "alg": alg_name,
                "output": [out_name, "Out"]
                })
                algorithms.append({
                    "name": alg_name,
                    "st": f"<![CDATA[State:={state_name};]]>"
                })
                for from_state in event_map[event]:
                    transitions.append({
                        "source": "S" + from_state.name,
                        "destination": "S"+state_name,
                        "condition": event.name
                    })
            else:
                #adiciona o estado original a lista de estados sem saida
                alg_name = "ALG"+state_name
                states.append({
                "name": "S"+state_name,
                "alg": alg_name
                })
                algorithms.append({
                    "name": alg_name,
                    "st": f"<![CDATA[State:={state_name};]]>"
                })
                # Cria estados auxiliares para cada evento com múltiplos from_states
                sufix = 'a'
                for event, from_states in event_map.items():
                    aux_state_name = f"S{state_name}_{sufix}"
                    out_name = "Out_" + event.name
                    states.append({
                        "name": aux_state_name,
                        "output": [out_name, "Out"]
                    })

                    for from_state in from_states:
                        transitions.append({
                            "source": "S" + from_state.name,
                            "destination": aux_state_name,
                            "condition": event
                        })

                    # Transição livre do auxiliar para o estado original
                    transitions.append({
                        "source": aux_state_name,
                        "destination": "S"+state_name,
                        "condition": "1"  # condição sempre verdadeira
                    })

                    sufix = chr(ord(sufix) + 1) #incrementação do sufixo a + 1 = b

        states, transitions = self.sugiyama_layout(states, transitions)

        data = {
            "fb_name": fb_name,
            "event_inputs": event_inputs,
            "event_outputs": event_outputs,
            "input_vars": input_vars,
            "output_vars": output_vars,
            "states": states,
            "transitions": transitions,
            "algorithms": algorithms
        }

        return data

    def generate_ms(self, automato, fb_name, eg_dict):
        #print(eg_dict)
        # Inicializa listas para eventos e variáveis
        initial_state = automato.initial_state.name
        start_name = "S" + initial_state + "_Start"

        # {nome : [related_vars]}
        event_inputs = {"Start" : None} # apenas o que gera transicao
        event_outputs = {"StartO" : None}
        output_vars = [{"name" : "State", "type" : "INT", "initialValue" : "1"}]
        states = [{"name" : "START", "comment" : "Initial State"}, {"name" : start_name, "output" : ["StartO"]}]
        transitions = [{"source" : "START", "destination" : start_name, "condition" : "Start"},
                       {"source" : start_name, "destination" : "S" + initial_state, "condition" : "1"},]
        algorithms = []
        hab_map = {}
        habilitations = []
        vars_list = ["State"]

        for event in automato.events: #geracao das variaveis de habilitacao
            if event.controllable:
                event_name = "En_"+event.name
                habilitations.append(event_name)
                output_vars.append({"name" : event_name, "type" : "BOOL", "initialValue" : "FALSE"})
                vars_list.append(event_name)

                #print("Event -> " + event.name)
                if eg_dict.get(event.name):
                    #print("Encontrado")
                    eg_dict[event.name]["ms_list"].append(event_name + "_" + fb_name)
                else:
                    keys = eg_dict.keys()
                    #print(event.name + " nao encontrado em:")
                    #print(keys)
        event_outputs["Out"] = vars_list

        for state in automato.states:
            from_state = state.name
            alg_name = "ALG"+from_state
            states.append({
            "name" : "S"+state.name,
            "output" : ["Out"], 
            "alg": alg_name
            })

            hab_map[from_state] = [] #inicializar key
            for transition in state.out_transitions:
                if transition.from_state != transition.to_state: #apenas eventos de transicoes nao laco
                    event_name = transition.event.name
                    
                    event_inputs[event_name] = None
                    to_state = transition.to_state.name
                    transitions.append({
                        "source" : "S" + from_state,
                        "destination" : "S" + to_state,
                        "condition" : event_name
                    })
                if transition.event.controllable: 
                    hab_name = "En_" + transition.event.name 
                    hab_map[from_state].append(hab_name)

        for state in automato.states:
            state_name = state.name
            alg_name = "ALG"+state_name
            habs_st = ""
            for habilitation in habilitations:
                hab_bool = str(habilitation in hab_map[state_name])
                habs_st += f"\n\t\t\t\t{habilitation}:={hab_bool.upper()};"
            alg = f"<![CDATA[State:={state_name};{habs_st}\n\t\t\t\t]]>"
            algorithms.append({
                "name" : alg_name,
                "st" : alg
            })

        states, transitions = self.sugiyama_layout(states, transitions)

        data = {
            "fb_name": fb_name,
            "event_inputs": event_inputs,
            "event_outputs": event_outputs,
            "input_vars": None,
            "output_vars": output_vars,
            "states": states,
            "transitions": transitions,
            "algorithms": algorithms
        }
        return data

    def generate_eg(self, event, eg_info):
        #{su_name: "SUx", event_name : "a2", enabled_states : [Sx, Sy...], ms_list : ["MSx", "MSy"...]}
        su_var = "State_"+eg_info["su_name"]

        vars = [su_var]
        condition_st = "" #a ser gerado com infos do su e do ms
        event_outputs = {"EO" : None}
        input_vars = [{"name": su_var, "type": "INT"}]
        states = [{"name" : "START", "comment" : "Initial State", "pos" : [0, 0]},
                  {"name":"State", "output":["EO"], "pos" : [1000, 0]}]


        #EI[En_a2_MSa and En_a2_MSb and (State_SU2=0)]
        ms_list = eg_info["ms_list"]
        if ms_list:
            condition_st = "EI[("
            condition_st += ms_list[0]
            vars.append(ms_list[0])
            input_vars.append({"name" : ms_list[0], "type" : "BOOL"})
            ms_list.pop(0)
            for ms in ms_list:
                c_st = " and " + ms
                vars.append(ms)
                condition_st += c_st
                input_vars.append({"name" : ms, "type" : "BOOL"})

            enabled_states = eg_info["enabled_states"]
            if enabled_states:
                condition_st += " and (" + su_var + "=" + enabled_states[0]
                enabled_states.pop(0)
                for en_state in enabled_states:     
                    condition_st += " or " + su_var + "=" + en_state
                condition_st += ")"
            condition_st += ")]"

        event_inputs = {"EI" : vars}
        transitions = [{"source": "START", "destination":"State", "condition":condition_st, "pos" : [660, 400]},
                    {"source":"State", "destination":"START", "condition":"1", "pos" : [660, -300]}]
        
        
        data = {
            "fb_name": "EG_" + event,
            "event_inputs": event_inputs,
            "event_outputs": event_outputs,
            "input_vars": input_vars,
            "output_vars": None,
            "states": states,
            "transitions": transitions,
            "algorithms": None
        }
        return data

 
    def sugiyama_layout(self, nodes, edges):
#       nodes = [{"name" : "START", "comment" : "Initial State"}, {"name" : start_name, "output" : ["StartO"]}]
#       edges = [{"source" : "START", "destination" : start_name, "condition" : "Start"},
#                      {"source" : start_name, "destination" : "S" + initial_state, "condition" : "1"},]

        nodes_dict = dict()
        for node in nodes:
            node["pos"] = [0, 0]
            nodes_dict[node["name"]] = node

        layer_count = 0
        layer_build = dict()
        #layer_build = {S1 : 1, S2 : 3, S3 : 1} it maps the node to its layer

        for edge in edges:
            dest_node = edge["destination"]
            if(layer_build.get(dest_node)):
                layer_build[dest_node] += 1
                layer_count = max(layer_build[dest_node], layer_count)
            else:
                node_id = dest_node
                layer_build[node_id] = 1
        
        layers  = dict()
        #layers = {1 : ["S1", "S3"], 3 : ["S2"]} maps the layer to a list of nodes
        for i in range(1, layer_count+1):
            layers[i] = []

        for node in layer_build.keys():
            layer = layer_build[node]
            layers[layer].append(node)

        for layer in layers:
            i=0
            for node in layers[layer]:
                x = layer * 1500
                y = i * 1500
                nodes_dict[node]["pos"] = [x, y]
                i+=1
        offset = 0
        increment = 50
        for edge in edges:
            src =  edge["source"]
            dest = edge["destination"]
            src_pos = nodes_dict[src]["pos"]
            dest_pos = nodes_dict[dest]["pos"]
            increment *= -1
            offset = (offset * -1) + increment
            edge_x = (src_pos[0] + dest_pos[0])/2 + offset
            edge_y = (src_pos[1] + dest_pos[1])/2 + offset
            edge["pos"] = [edge_x, edge_y]

        nodes = nodes_dict.values()

        return nodes, edges
