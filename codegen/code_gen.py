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
    templates_name = ['generic_iec61499.fbt']
    template_path = 'codegen/templates'
#provavelmente não preciso da maioria das funções já que com automato consigo todas as informações necessarias
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_device('IEC61499')
        self.set_template_path(self.template_path)

    def generate_sup(self, automaton_list):
        data_pos = dict()
        #state_map = dict() 
        #this implementation generates one function block for each automata
        #so there is no need to use a state_map, as the states are stored by their names
        states = list()
        data = list()
        event_map = list()
        events = set()
        initial_state = list()

        for k_automaton, automaton in enumerate(automaton_list):
            data_pos[k_automaton] = len(data)
            initial_state= automaton.initial_state

            for state in automaton.states:
                states.append(state)
            
            for state in automaton.states:
                data.append(len(state.out_transitions))
                for transition in state.out_transitions:
                    if transition.event.name not in [ev.name for ev in events]:
                        events.add(transition.event)
                    data.append(f'EV_{transition.event.name}')
                    data.append(transition.from_state)
                    data.append(transition.to_state)

        for automaton in automaton_list:
            event_map.append([True if event.name in [ev.name for ev in automaton.events] else False for event in events])

        """
        print("Data list:")
        for info in data:
            print(info)
        print("end")
        print("data_pos list:")
        for key, value in data_pos.items():
            print(f"{key}->{value}") 
        print("end")
        print("states list:")
        for state in states:
            print(state)
        print("end")
        print("events list:")
        for info in events:
            print(info)
        print("end")
        print("event_map list:")
        for info in event_map:
            print(info)
        print("end")
        print("initial_state:")
        print(initial_state)
        print("end")
        """
        return data, data_pos, states, events, event_map, initial_state

    def write(self, automata_list, vars_dict, output_path):
        for automato in automata_list:
            print(type(automato))
            print(automato.get_name())
            print(automato)

        eg_list = list()
        """
            self.path = path
            self.su_name = su_name
            self.event_name = event_name
            self.enabled_states = enabled_states
            self.ms_list = ms_list
        """
        for automato in automata_list:
            if automato._name[0] == "G":
                fb_name = "SU"+automato._name[1]+".fbt"
                output_dict = self.generate_su(automato, fb_name, eg_list)
                output_dict.update(vars_dict)
                self._write(output_path, output_dict)


            elif automato._name[:2] == "RS":
                fb_name = "MS"+automato._name[2]+".fbt"
                output_dict = self.generate_ms(automato, fb_name, eg_list)
                output_dict.update(vars_dict)
                self._write(output_path, output_dict)

            else:
                print("File error: " + automato._name)
    
        if eg_list:
            for eg in eg_list:
                output_dict = self.generate_eg(eg)
                output_dict.update(vars_dict)
                self._write(output_path, output_dict)

    
    def generate_su(self, automato, fb_name, eg_list):
        #[{"name":"a1"}, {"name:b2"}]
        event_inputs = list()
        event_outputs = list()

        #[{"name": "State", "type": "INT"}, {"name": "En_a2", "type": "BOOL"}],
        input_vars = list()
        output_vars = list()

        #[{"name": "S0", "alg": "ALG2", "output": "Out"}]
        states = list()

        #[{"source": "START", "destination": "S0", "condition": "Start"}],
        transitions = list()

        #[{"name": "ALG2", "st": "State := 2;"}]
        algorithms = list()

        #######################################################################################################
        ###                              Aqui ficara o processamento dos dados                              ###
        ###                            Como descobrir se eventos sao controláveis                           ###
        #######################################################################################################
        
        data = {
            "fb_name": automato._name,
            "event_inputs": event_inputs,
            "event_outputs": event_outputs,
            "input_vars": input_vars,
            "output_vars": output_vars,
            "states": states,
            "transitions": transitions,
            "algorithms": algorithms
        }   
        print(data)
        
        return data

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
        return res

    def add_extra_properties(self, events):
        return {}

    def generate_strings(self, automatons):
        data, data_pos, states, events, event_map, initial_state = self.generate_sup(automatons)
        print(automatons)
        result = {
            'automaton_list': automatons,
            'events': events,
            'event_names': self._gen_str([f'EV_{event.name}' for event in events]),
            'data': data,
            'ev_controllable': self._gen_str(['1' if event.controllable else '0' for event in events]),
            'sup_init_state': self._gen_str(initial_state),
            'sup_current_state': self._gen_str(initial_state),
            'sup_data_pos': self._gen_str(data_pos),
            'sup_data': self._gen_str(data),
            'sup_event_map': self._gen_str([[1 if event else 0 for event in automaton_event_list] for automaton_event_list in event_map])
        }
        """
        print("The generate_strings result is ready:")
        for key in result:
            print(key)
            for value in result[key]:
                print(f"{key}->{value}")
        print("end")
        """
        result.update(self.add_extra_properties(events))
        return result

    