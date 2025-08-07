class InvalidModelException(Exception):
    def __init__(self):
        super().__init__("InvalidModel: This model is invalid or not supported by the system.")