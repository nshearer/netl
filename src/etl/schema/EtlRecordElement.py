from EtlSchemaElement import EtlSchemaElement

class EtlRecordElement(EtlSchemaElement):
    '''An element that stores a record'''

    def __init__(self, record_schema):
        '''Init 

        @param record_schema:
            The schema of the record that this 
        '''
        self.__schema = record_schema
        super(EtlRecordElement, self).__init__()


    @property
    def record_schema(self):
        return self.__schema


    def __eq__(self, other):
        if super(EtlListElement, self).__eq__(other):
            if self.__schema == other.__schema:
                return True
            return False
        return False        