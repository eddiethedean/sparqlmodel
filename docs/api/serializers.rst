Serializers
===========

Thin wrappers over `TripleModel <https://github.com/eddiethedean/triplemodel>`_ ``infer_format``,
``load_graph``, and ``SPARQLModel.serialize()``. Prefer ``SPARQLModel.serialize()`` and
``SPARQLModel.parse()`` for file I/O. See :func:`~sparqlmodel.serializers.model_to_jsonld` and
:func:`~sparqlmodel.serializers.model_from_jsonld` for ORM dict helpers (not identical to
graph JSON-LD export).

.. automodule:: sparqlmodel.serializers
   :members:
   :show-inheritance:
