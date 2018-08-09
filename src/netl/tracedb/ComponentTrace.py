

from .TraceObject import TraceData, TraceAction

class ComponentTrace(TraceData):
    '''A component in the ETL'''

    TABLE = 'components'

    CREATE_STATEMENTS = (
        """\
            create table components (
              id          int primary key,
              name        text,
              class       text,
              state_code  text,
              started_at  timestamp,
              ended_at    timestamp)
        """,
    )

    INIT_STATE = 'init'
    RUNNING_STATE = 'running'
    FINISHED_STATE = 'finshed'
    ERROR_SATE = 'error'

    @staticmethod
    def list_components(trace_db):
        results = trace_db.execute_select("select * from components")
        for row in results:
            yield ComponentTrace(trace_db, **row)


    def list_ports(self):
        return self.db.list_ports_for(self.id)

    def list_input_ports(self):
        return self.db.list_ports_for(self.id, port_type='i')

    def list_output_ports(self):
        return self.db.list_ports_for(self.id, port_type='o')


    STATE_COLORS = {
        INIT_STATE:     '#FFC107', # yellow
        RUNNING_STATE:  '#08B530', # green
        FINISHED_STATE: '#007BFF', # blue
        ERROR_SATE:     '#DC3545', # red
    }
    @property
    def state_color(self):
        try:
            return self.STATE_COLORS[self.state_code]
        except KeyError:
            return '#000000'


class TraceNewComponent(TraceAction):

    def __init__(self, component_id, name, clsname, state):
        '''
        Tell the tracer about a component

        :param component_id: Unique, integer ID for this component
        :param name: Name of the component
        :param clsname: Class name of the component
        :param state: Code that represents the state of the component
        '''
        super(TraceNewComponent, self).__init__()
        self.component_id = component_id
        self.name = name
        self.clsname = clsname
        self.state = state

    def record_trace_to_db(self, trace_db, commit):
        trace_db.execute_update("""
            insert into components (id, name, class, state_code, started_at)
            values (?, ?, ?, ?, ?)
            """, (int(self.component_id), self.name, self.clsname, self.state, self.ts),
                                commit=commit)


class TraceComponentStateChange(TraceAction):

    def __init__(self, component_id, state):
        '''
        Update the status of the component

        :param component_id: nique, integer ID for this component
        :param state: New state code
        '''
        super(TraceComponentStateChange, self).__init__()
        self.component_id = component_id
        self.state_code = state

    def record_trace_to_db(self, trace_db, commit):
        trace_db.execute_update("""
            update components
            set state_code = ?
            where id = ?
            """, (self.state_code, int(self.component_id)), commit=commit)
        if self.state_code in (ComponentTrace.FINISHED_STATE, ComponentTrace.ERROR_SATE):
            trace_db.execute_update("""
                update components
                set ended_at = ?
                where id = ?
                """, (self.ts, int(self.component_id)), commit=commit)