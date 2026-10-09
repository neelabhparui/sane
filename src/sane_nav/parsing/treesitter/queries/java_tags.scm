;; S.A.N.E. Java Tags Query
;; Adapted in part from Aider (Apache 2.0) - see NOTICE

(package_declaration
  [(scoped_identifier) (identifier)] @package)

(class_declaration
  name: (identifier) @name
  body: (class_body) @body) @definition.class

(interface_declaration
  name: (identifier) @name
  body: (interface_body) @body) @definition.interface

(record_declaration
  name: (identifier) @name
  body: (class_body) @body) @definition.record

(enum_declaration
  name: (identifier) @name
  body: (enum_body) @body) @definition.enum

(constructor_declaration
  name: (identifier) @name
  parameters: (formal_parameters) @parameters
  body: (constructor_body) @body) @definition.constructor

(method_declaration
  name: (identifier) @name
  parameters: (formal_parameters) @parameters
  body: (block)? @body) @definition.method

(superclass
  (type_identifier) @reference.extends)

(super_interfaces
  (type_list
    (type_identifier) @reference.implements))

(method_invocation
  object: (_)? @receiver
  name: (identifier) @name) @reference.call

(object_creation_expression
  type: (type_identifier) @name) @reference.instantiation
