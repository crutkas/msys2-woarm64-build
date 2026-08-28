require "json"
require "psych"

abort "usage: parse-yaml.rb PATH" unless ARGV.length == 1

document = Psych.safe_load(
  File.read(ARGV[0], encoding: "UTF-8"),
  permitted_classes: [],
  permitted_symbols: [],
  aliases: true
)
# Psych follows YAML 1.1 boolean keys; GitHub workflows treat `on` as YAML 1.2 text.
document["on"] = document.delete(true) if document.is_a?(Hash) && document.key?(true) && !document.key?("on")
STDOUT.write(JSON.generate(document))
