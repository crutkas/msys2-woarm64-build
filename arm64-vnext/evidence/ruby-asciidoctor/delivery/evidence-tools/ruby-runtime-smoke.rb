require 'rbconfig'
require 'rubygems'
require 'json'
require 'digest'
require 'zlib'
require 'openssl'
require 'psych'
require 'fiddle'
require 'strscan'

raise 'Wrong Ruby version' unless RUBY_VERSION == '4.0.6'
raise 'Wrong Ruby platform' unless RUBY_PLATFORM.start_with?('aarch64-mingw')
raise 'Zlib round trip failed' unless Zlib::Inflate.inflate(Zlib::Deflate.deflate('native ruby')) == 'native ruby'
raise 'OpenSSL digest mismatch' unless OpenSSL::Digest::SHA256.hexdigest('abc') == Digest::SHA256.hexdigest('abc')
raise 'Psych YAML round trip failed' unless Psych.safe_load(Psych.dump({'answer' => 42})) == {'answer' => 42}
raise 'Strscan failed' unless StringScanner.new('native ruby').scan(/\w+/) == 'native'
raise 'Large integer arithmetic failed' unless ((2**1024) / (2**512)) == 2**512
kernel = Fiddle.dlopen('kernel32.dll')
get_pid = Fiddle::Function.new(kernel['GetCurrentProcessId'], [], Fiddle::TYPE_LONG)
raise 'Native libffi call failed' unless get_pid.call == Process.pid

ready, release = ARGV
raise 'Expected ready and release paths' unless ready && release
report = {
  pid: Process.pid,
  ruby: RUBY_DESCRIPTION,
  platform: RUBY_PLATFORM,
  executable: RbConfig.ruby,
  compiler: RbConfig::CONFIG['CC'],
  compiler_version: RbConfig::CONFIG['CC_VERSION_MESSAGE'],
  gem_default_dir: Gem.default_dir,
  path: ENV.fetch('PATH'),
  zlib: Zlib::ZLIB_VERSION,
  openssl: OpenSSL::OPENSSL_LIBRARY_VERSION,
  psych: Psych::VERSION,
  loaded_native_extensions: $LOADED_FEATURES.grep(/\.(so|dll)\z/),
  tested: %w[zlib openssl psych fiddle strscan json digest big_integer]
}
File.write("#{ready}.tmp", JSON.pretty_generate(report))
File.rename("#{ready}.tmp", ready)
deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 60
until File.file?(release)
  raise 'Native module observer did not release the process' if Process.clock_gettime(Process::CLOCK_MONOTONIC) > deadline
  sleep 0.05
end
puts JSON.generate(report)
