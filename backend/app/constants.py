"""Shared limits. Embedding width is fixed until a provider is chosen."""

EMBEDDING_DIMENSIONS = 1024
MIN_TEXT_ALNUM = 80
CHUNK_SIZE = 1200
MAX_FIELD_LENGTH = 4000
MAX_QUOTE_LENGTH = 1000
MAX_NAME_LENGTH = 200
MAX_ERROR_LENGTH = 120

# Attributes the hub must never infer or accept from a model.
BLOCKED_FIELDS = frozenset(
    {
        "nationality",
        "age",
        "gender",
        "religion",
        "race",
        "ethnicity",
        "date_of_birth",
        "dob",
        "marital_status",
        "sex",
    }
)
