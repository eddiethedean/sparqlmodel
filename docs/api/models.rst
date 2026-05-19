Models and fields
=================

:class:`~sparqlmodel.model.SPARQLModel` subclasses `Pydantic v2 <https://docs.pydantic.dev/latest/>`__
:class:`pydantic.BaseModel`. Field types and constraints are validated on construction and when
loading from the graph (hydration). For patterns and the validation stack, see
:doc:`../guides/models`.

.. automodule:: sparqlmodel.model
   :members:
   :show-inheritance:

.. automodule:: sparqlmodel.fields
   :members:
   :show-inheritance:

.. automodule:: sparqlmodel.types
   :members:
   :show-inheritance:
