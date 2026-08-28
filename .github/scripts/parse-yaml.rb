require "json"
require "psych"

abort "usage: parse-yaml.rb PATH" unless ARGV.length == 1
abort "unapproved Ruby version" unless RUBY_VERSION == "3.2.3"
abort "unapproved Psych version" unless Psych::VERSION == "5.1.2"

text = File.binread(ARGV[0]).force_encoding(Encoding::UTF_8)
abort "YAML is not strict UTF-8" unless text.valid_encoding?
abort "YAML BOM is forbidden" if text.start_with?("\uFEFF")

stream = Psych.parse_stream(text)
abort "YAML must contain exactly one document" unless stream.children.length == 1

reject_duplicate_keys = lambda do |node|
  if node.is_a?(Psych::Nodes::Mapping)
    keys = {}
    node.children.each_slice(2) do |key, value|
      abort "complex YAML mapping keys are forbidden" unless key.is_a?(Psych::Nodes::Scalar)
      identity = [key.tag, key.value]
      abort "duplicate YAML mapping key" if keys.key?(identity)
      keys[identity] = true
      reject_duplicate_keys.call(value)
    end
  else
    node.children.each { |child| reject_duplicate_keys.call(child) } if node.respond_to?(:children)
  end
end
reject_duplicate_keys.call(stream)

document = Psych.safe_load(
  text,
  permitted_classes: [],
  permitted_symbols: [],
  aliases: false
)
# Psych follows YAML 1.1 boolean keys; GitHub workflows treat `on` as YAML 1.2 text.
document["on"] = document.delete(true) if document.is_a?(Hash) && document.key?(true) && !document.key?("on")
STDOUT.write(JSON.generate(document))
