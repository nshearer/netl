import os
import sqlite3
from threading import Lock

from .TraceObject import TraceAction

from .ComponentTrace import ComponentTrace
from .PortTrace import PortTrace
from .EnvelopeTrace import EnvelopeTrace
from .RecordTrace import RecordTrace
from .ConnectionTrace import ConnectionTrace

from ..utils import ResultBuffer


class TraceDB:
    '''
    Interface to the ETL tracing database tracking ETL progress

    This object serves as a single handle to the database connection
    to use is a multi-threaded environment for both updating the database
    with new events and reading the trace data.

    According to the manual for sqlite3:

        By default, check_same_thread is True and only the creating
        thread may use the connection. If set False, the returned
        connection may be shared across multiple threads. When
        using multiple threads with the same connection writing
        operations should be serialized by the user to avoid
        data corruption.

    Also note that not committing will lock the database:

        When a database is accessed by multiple connections, and
        one of the processes modifies the database, the SQLite
        database is locked until that transaction is committed.


    +-------------+   TraceAction*      +-----------+
    | ETL Threads +------------------Q--> EtlTracer |
    | (multiple)  |                     |  Thread   |
    +-------------+                     +-----------+
                                        |  TraceDB  |
                                        +--+--------+
                                           |
                                        +--v--------+
                                        | Database  |
                                        +--+--------+
                                           |
    +-------------+                     +--+--------+
    |  Analyze    <---------------------+  TraceDB  |
    |  Threads    |                     | TraceData |
    +-------------+                     +-----------+

    '''

    VERSION='dev'

    INIT_STATE = 'init'
    RUNNING_STATE = 'running'
    FINISHED_STATE = 'finished'
    ERROR_STATE = 'error'

    CREATE_STATEMENTS = (
        """\
        create table etl(
          state_code  text,
          db_ver      text)
        """,
    )


    def __init__(self, path, mode='r'):

        if mode == 'r':
            self.__readonly = True
            if not os.path.exists(path):
                raise Exception("TraceDB %s doesn't exist" % (path))
        elif mode == 'rw':
            self.__readonly = False
        else:
            raise Exception("mode must be r or rw")

        self.__db = sqlite3.connect(path, check_same_thread=False)
        self.__db_lock = Lock()


    # === sqlite3 DB access methods protected by lock =====================

    def execute_select(self, sql, parms=None, return_dict=True):
        '''
        Execute SQL to select data from the database (no modifications)

        execute_select("""
            select name_last, age
            from people
            where name_last=:who and age=:age
            """,  {"who": who, "age": age})

        Note: theoretically sqlite3 supports multiple cursors open at once,
        but I've had trouble with such.  So this method retrieves all results,
        closes the cursor, and returns the results.
        '''

        with self.__db_lock:
            cursor = self.__db.cursor()
            results = ResultBuffer()

            if parms:
                cursor.execute(sql, parms)
            else:
                cursor.execute(sql)

            for row in cursor:
                if return_dict:
                    d = {}
                    for idx, col in enumerate(cursor.description):
                        d[col[0]] = row[idx]
                    row = d
                results.add(row)

        # Stream back results (lock released)
        for row in results.all():
            yield row


    def execute_select_one(self, sql, parms=None, return_dict=True):
        for row in self.execute_select(sql, parms, return_dict):
            return row
        raise Exception("SQL statement returned no results: " + sql)


    def execute_count(self, sql, parms=None):
        row = self.execute_select_one(sql, parms, return_dict=False)
        return row[0]


    def execute_update(self, sql, parms=None, commit=True):
        '''Execute SQL that writes to the DB'''
        self.assert_readwrite()
        with self.__db_lock:

            if parms is None:
                self.__db.execute(sql)
            else:
                self.__db.execute(sql, parms)

            if commit:
                self.__db.commit()


    def commit(self):
        '''Request a commit to DB'''
        self.assert_readwrite()
        with self.__db_lock:
            self.__db.commit()


    @property
    def etl_state_desc(self):
        code = self.etl_status()
        if code == self.INIT_STATE:
            return "Initializing"
        elif code == self.RUNNING_STATE:
            return "Running"
        elif code == self.FINISHED_STATE:
            return "Finished"
        elif code == self.ERROR_STATE:
            return "Error"


    # === Trace DB logic and structure ====================================


    # @property
    # def sqlite3db(self):
    #     if self.__db is None:
    #         raise Exception("Database closed")
    #     return self.__db


    @property
    def readonly(self):
        return self.__readonly


    def assert_readwrite(self):
        if self.__readonly:
            raise Exception("Database open for read only")


    def close(self):
        self.__db.close()
        self.__db = None


    @staticmethod
    def create(path, mode='rw'):

        if os.path.exists(path):
            raise Exception("Trace DB file already exists: " + path)
        db = sqlite3.connect(path)

        create_statments = list(TraceDB.CREATE_STATEMENTS)
        create_statments.extend(ComponentTrace.CREATE_STATEMENTS)
        create_statments.extend(PortTrace.CREATE_STATEMENTS)
        create_statments.extend(ConnectionTrace.CREATE_STATEMENTS)
        create_statments.extend(EnvelopeTrace.CREATE_STATEMENTS)
        create_statments.extend(RecordTrace.CREATE_STATEMENTS)

        for sql in create_statments:
            db.cursor().execute(sql)

        db.cursor().execute("""
            insert into etl (state_code, db_ver)
            values (?, ?)
            """, (TraceDB.INIT_STATE, TraceDB.VERSION))

        db.commit()
        db.close()
        return TraceDB(path)

    # -- Queries -----------------------------------------------------------------------

    def etl_status(self):
        return self.execute_select_one("select state_code from etl")['state_code']

    def list_components(self):
        return ComponentTrace.list_components(self)

    def list_ports_for(self, component_id, port_type=None):
        return PortTrace.list_ports_for(self, component_id, port_type)

    def list_connections(self):
        return ConnectionTrace.list_connections(self)

    def get_connection_stats(self):
        return EnvelopeTrace.get_connection_stats(self)



class TraceETLStateChange(TraceAction):

    def __init__(self, state):
        '''
        Update the status of the ETL

        :param state: New state code
        '''
        super(TraceETLStateChange, self).__init__()
        self.state_code = state

    def record_trace_to_db(self, trace_db, commit):
        trace_db.execute_update("""
            update etl
            set state_code = ?
            """, (self.state_code, ), commit=True)


# TODO: Extra trace objects

                # # Record Derivation Trace Table: Trace when one record value is referenced to calucate the value of another
                # db.cursor().execute("""
                #     create table record_derivation (
                #       ref_record_id     int,
                #       ref_record_attr   text,
                #       calc_record_id    int,
                #       calc_record_attr  text)
                # """)
                #
                # # Component Status Table: Large record storage
                # db.cursor().execute("""
                #     create table large_records (
                #       id                int primary key)
                # """)
                # db.cursor().execute("""
                #     create table large_record_data (
                #       large_rec_id      int,
                #       chunk_num         int,
                #       data              text)
                # """)