;; S.A.N.E. Kotlin Tags Query

(package_header
  [(identifier) (simple_identifier)] @package)

(class_declaration
  (type_identifier) @name
  (class_body)? @body) @definition.class

(object_declaration
  (type_identifier) @name
  (class_body)? @body) @definition.object

(companion_object
  (class_body)? @body) @definition.companion

(function_declaration
  (simple_identifier) @name
  (function_value_parameters)? @parameters
  (function_body)? @body) @definition.function

(secondary_constructor
  (function_value_parameters)? @parameters
  (function_body)? @body) @definition.constructor

(delegation_specifier
  (constructor_invocation
    (user_type (type_identifier) @reference.extends)))

(delegation_specifier
  (user_type (type_identifier) @reference.implements))

(call_expression
  (navigation_expression
    (_) @receiver
    (navigation_suffix
      (simple_identifier) @name))) @reference.call

(call_expression
  (simple_identifier) @name) @reference.call
