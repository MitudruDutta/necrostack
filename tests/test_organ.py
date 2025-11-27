"""Property-based tests for Organ base class."""

from hypothesis import given, settings
from hypothesis import strategies as st

from necrostack.core.event import Event
from necrostack.core.organ import Organ

# Strategy for generating valid class names (Python identifier style)
valid_class_names = st.from_regex(r"[A-Z][A-Za-z0-9_]{0,30}", fullmatch=True)


def create_organ_class(class_name: str) -> type[Organ]:
    """Dynamically create an Organ subclass with the given name."""

    def handle(self, event: Event) -> None:
        return None

    return type(
        class_name,
        (Organ,),
        {
            "listens_to": ["TEST_EVENT"],
            "handle": handle,
        },
    )


# **Feature: necrostack-framework, Property 5: Organ Name Defaulting**
# **Validates: Requirements 2.4**
@given(class_name=valid_class_names)
@settings(max_examples=100)
def test_organ_name_defaults_to_class_name(class_name: str):
    """For any Organ subclass instantiated without an explicit name argument,
    the name attribute SHALL equal the class name.
    """
    # Create a dynamic Organ subclass with the generated class name
    organ_class = create_organ_class(class_name)

    # Instantiate without explicit name
    organ = organ_class()

    # Verify name defaults to class name
    assert organ.name == class_name


# Additional test: explicit name overrides default
@given(
    class_name=valid_class_names,
    explicit_name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
)
@settings(max_examples=100)
def test_organ_explicit_name_overrides_default(class_name: str, explicit_name: str):
    """For any Organ subclass instantiated with an explicit name argument,
    the name attribute SHALL equal the provided name, not the class name.
    """
    organ_class = create_organ_class(class_name)

    # Instantiate with explicit name
    organ = organ_class(name=explicit_name)

    # Verify explicit name is used
    assert organ.name == explicit_name
    assert organ.name != class_name or explicit_name == class_name
