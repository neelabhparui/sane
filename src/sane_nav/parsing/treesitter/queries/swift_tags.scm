;; S.A.N.E. Swift Tags Query

(class_declaration
  "class"
  name: (type_identifier) @name
  body: (class_body)? @body) @definition.class

(class_declaration
  "struct"
  name: (type_identifier) @name
  body: (class_body)? @body) @definition.struct

(class_declaration
  "enum"
  name: (type_identifier) @name
  body: (enum_class_body)? @body) @definition.enum

(protocol_declaration
  (type_identifier) @name
  (protocol_body)? @body) @definition.protocol

(init_declaration
  (function_body)? @body) @definition.constructor

(function_declaration
  (simple_identifier) @name
  (function_body)? @body) @definition.function

(protocol_function_declaration
  (simple_identifier) @name) @definition.function

(inheritance_specifier
  (user_type (type_identifier) @reference.type))

(call_expression
  (navigation_expression
    (_) @receiver
    (navigation_suffix
      (simple_identifier) @name))) @reference.call

(call_expression
  (simple_identifier) @name) @reference.call
