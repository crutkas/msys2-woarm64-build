#!/usr/bin/perl
use strict;
use warnings;

use Digest::SHA qw(sha256_hex);

my $path = "test/recipes/82-test_ocsp_cert_chain.t";
open(my $input, "<:raw", $path) or die "cannot read $path: $!";
local $/;
my $text = <$input>;
close($input) or die "cannot close $path: $!";

die "unexpected OpenSSL OCSP test source\n"
    unless sha256_hex($text) eq "924b413e933d24683d2e0e58fddd9c0be563f1e2035e06697f8c66a5a48ce166";

my $imports = "use IPC::Open3;\n";
die "unexpected OpenSSL OCSP import anchor\n"
    unless $text =~ s/\Q$imports\E/$imports . "use IO::Select;\n"/e;

my $command = <<'ORIGINAL';
my $shlib_wrap   = bldtop_file("util", "shlib_wrap.sh");
my $apps_openssl = bldtop_file("apps", "openssl");
ORIGINAL
my $relayed_command = <<'REPAIRED';
my $shlib_wrap   = bldtop_file("util", "shlib_wrap.sh");
my $apps_openssl = bldtop_file("apps", "openssl");
my @openssl_cmd  = ($shlib_wrap);
push(@openssl_cmd, "/bin/bash", $ENV{WOARM64_NATIVE_EXEC})
    if defined($ENV{WOARM64_NATIVE_EXEC});
push(@openssl_cmd, $apps_openssl);
REPAIRED
die "unexpected OpenSSL OCSP command anchor\n"
    unless $text =~ s/\Q$command\E/$relayed_command/;

my $direct_command = '$shlib_wrap, $apps_openssl';
my $direct_calls = () = $text =~ /\Q$direct_command\E/g;
die "unexpected OpenSSL OCSP direct command count\n"
    unless $direct_calls == 3;
$text =~ s/\Q$direct_command\E/\@openssl_cmd/g;

my $wait = <<'ORIGINAL';
    waitpid($s_client_pid, 0);
ORIGINAL
my $lifecycle = <<'REPAIRED';
    close($s_client_i) or die "failed to close s_client stdin: $!";
    my $s_client_output = IO::Select->new($s_client_o, $s_client_e);
    while ($s_client_output->count) {
        for my $stream ($s_client_output->can_read) {
            my $line = <$stream>;
            if (defined($line)) {
                print($line);
            } else {
                $s_client_output->remove($stream);
                close($stream);
            }
        }
    }

    waitpid($s_client_pid, 0);
REPAIRED
die "unexpected OpenSSL OCSP client lifecycle anchor\n"
    unless $text =~ s/\Q$wait\E/$lifecycle/;
die "unexpected repaired OpenSSL OCSP test source\n"
    unless sha256_hex($text) eq "7ec36d0dfd1e49cd365f4c1747ab92b8821ac9e58ea239e9758090ca81b33491";

open(my $output, ">:raw", $path) or die "cannot write $path: $!";
print {$output} $text or die "cannot update $path: $!";
close($output) or die "cannot close updated $path: $!";
