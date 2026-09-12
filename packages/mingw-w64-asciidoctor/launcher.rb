require 'rubygems'

gem_home = File.expand_path('../ruby/gems/4.0.0', __dir__)
Gem.use_paths(gem_home, [gem_home, Gem.default_dir])
load Gem.bin_path('asciidoctor', 'asciidoctor', '= 2.0.26')
