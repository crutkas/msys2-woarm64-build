#!/usr/bin/perl
use strict;
use warnings;

use Digest::SHA qw(sha256_hex);

sub update_file {
    my ($path, $original_hash, $repaired_hash, $transform) = @_;
    open(my $input, "<:raw", $path) or die "cannot read $path: $!";
    local $/;
    my $text = <$input>;
    close($input) or die "cannot close $path: $!";

    my $current_hash = sha256_hex($text);
    return if $current_hash eq $repaired_hash;
    die "unexpected OpenSSL test source: $path ($current_hash)\n"
        unless $current_hash eq $original_hash;
    $transform->(\$text);
    $text =~ s/\r\n/\n/g;
    my $actual_repaired_hash = sha256_hex($text);
    die "unexpected repaired OpenSSL test source: $path ($actual_repaired_hash)\n"
        unless $actual_repaired_hash eq $repaired_hash;

    open(my $output, ">:raw", $path) or die "cannot write $path: $!";
    print {$output} $text or die "cannot update $path: $!";
    close($output) or die "cannot close updated $path: $!";
}

update_file(
    "test/recipes/01-test_symbol_presence.t",
    "61aff99e80740f9355b3752180331d9696c1eca008e432bf98a992eb9bf5d8a7",
    "24ff501453f0200695c1e5b9cd38a3b2a0b30029337dc236648e055da5de5e78",
    sub {
        my ($text) = @_;
        my $old = '    my $shlib_cmd = "nm -DPg $shlibpath{$_} 2> /dev/null";';
        my $new = <<'REPAIRED';
    my $target_is_mingw = config('target') =~ m|^mingw|;
    my $shlib_nm_flags = $target_is_mingw ? '-Pg' : '-DPg';
    my $shlib_cmd = "nm $shlib_nm_flags $shlibpath{$_} 2> /dev/null";
REPAIRED
        chomp($new);
        die "unexpected symbol-presence anchor\n"
            unless $$text =~ s/\Q$old\E/$new/;

        my $old_def_cmd =
            '            my $def_cmd = "$^X $mkdefpath --ordinals $def_path --name $_ --OS linux 2> /dev/null";';
        my $new_def_cmd = <<'REPAIRED';
            my $def_os = $target_is_mingw ? 'mingw' : 'linux';
            my $def_cmd = "$^X $mkdefpath --ordinals $def_path --name $_ --OS $def_os 2> /dev/null";
REPAIRED
        $new_def_cmd =~ s/\R+\z//;
        die "unexpected symbol-definition command anchor\n"
            unless $$text =~ s/\Q$old_def_cmd\E/$new_def_cmd/;

        my $old_def_parse = <<'ORIGINAL';
        @def_lines =
            sort
            map { s|;||; s|\s+||g; $_ }
            grep { $in_global = 1 if m|global:|;
                   $in_global = 0 if m|local:|;
                   $in_global = 0 if m|\}|;
                   $in_global && m|;|; } @def_lines;
ORIGINAL
        chomp($old_def_parse);
        my $new_def_parse = <<'REPAIRED';
        if ($target_is_mingw) {
            @def_lines =
                sort
                map { s|^\s+||; s|\s+.*$||; $_ }
                grep m|^\s+\S|, @def_lines;
        } else {
            @def_lines =
                sort
                map { s|;||; s|\s+||g; $_ }
                grep { $in_global = 1 if m|global:|;
                       $in_global = 0 if m|local:|;
                       $in_global = 0 if m|\}|;
                       $in_global && m|;|; } @def_lines;
        }
REPAIRED
        chomp($new_def_parse);
        die "unexpected symbol-definition parser anchor\n"
            unless $$text =~ s/\Q$old_def_parse\E/$new_def_parse/;
    }
);

update_file(
    "test/recipes/02-test_errstr.t",
    "e3506d0d5a4754802d8543c3d49bdf02110b84be03e08c18ce8c6c7b190503d5",
    "82d215ec1bba99a76b603248fc96cf99c8d4e4fa686a4115db3388f119cab0ae",
    sub {
        my ($text) = @_;
        my $old = "    if \$^O eq 'msys' or \$^O eq 'MSWin32';";
        my $new = <<'REPAIRED';
    if (($ENV{WOARM64_NATIVE_TARGET_OS} // '') eq 'MSWin32'
        or $^O eq 'msys' or $^O eq 'MSWin32');
REPAIRED
        chomp($new);
        die "unexpected errstr platform anchor\n"
            unless $$text =~ s/\Q$old\E/$new/;
    }
);

update_file(
    "test/bioprinttest.c",
    "65c2f4f59bde5ffcb9cca4f6fcce5be31d4a149dbaa15dffbb980c9dda407afa",
    "169c183781137fb55f8fe943fea45cdeeb35e9d074311a10aaab2b14320582bd",
    sub {
        my ($text) = @_;
        my $old = <<'ORIGINAL';
    { { .i = 0x1337 }, AT_INT, "|%2147483639.x|",
        "|                                                              ",
        .skip_libc_ret_check = true, .exp_ret = -1 },
ORIGINAL
        chomp($old);
        my $new = <<'REPAIRED';
    { { .i = 0x1337 }, AT_INT, "|%2147483639.x|",
        "|                                                              ",
#if defined(__MINGW32__)
        /* MinGW snprintf() overflows the stack for this huge width. */
        .skip_libc_check = true,
#endif
        .skip_libc_ret_check = true, .exp_ret = -1 },
REPAIRED
        chomp($new);
        die "unexpected bioprint MinGW libc anchor\n"
            unless $$text =~ s/\Q$old\E/$new/;
    }
);

update_file(
    "test/recipes/20-test_speed.t",
    "f7fe0f06bc9d685b5252bb2d934372c9eeff2ff86e63e97b0d19f8b4566b2cf7",
    "0f12203139df72c6a5ca261e109de01359a39618d21a09a337917fb518d7a140",
    sub {
        my ($text) = @_;
        my $old = '       if $^O =~ /^(VMS|MSWin32)$/;';
        my $new = <<'REPAIRED';
       if (($ENV{WOARM64_NATIVE_TARGET_OS} // '') eq 'MSWin32'
           || $^O =~ /^(VMS|MSWin32)$/);
REPAIRED
        chomp($new);
        die "unexpected speed platform anchor\n"
            unless $$text =~ s/\Q$old\E/$new/;
    }
);

update_file(
    "test/recipes/20-test_app_s_client.t",
    "a0ea6a5df2bd802be852125696caf887a8832ce3581315bc66834db5db22b271",
    "db48c9ebde08a1ffd3fa97d0e34bcd936e87dbb4e8296e3dbad449d089d17219",
    sub {
        my ($text) = @_;
        my $old = 'if (open my $fh, "<", $command_file) {';
        my $new = 'if (open my $fh, "<:raw", $command_file) {';
        die "unexpected Sieve command capture anchor\n"
            unless $$text =~ s/\Q$old\E/$new/;
    }
);

update_file(
    "test/recipes/25-test_verify.t",
    "5ba87fccf8a3f9b0d65fdb442744829d9873eebe3d3ca51aa74a8da80515ecc6",
    "3f9cafc1ec35ecd5b0dea6d18f1fc8c0c39da148733464076450143cfc83eb21",
    sub {
        my ($text) = @_;
        my $old_skip = '        if $^O =~ /^(MSWin32|VMS)$/;';
        my $new_skip = <<'REPAIRED';
        if (($ENV{WOARM64_NATIVE_TARGET_OS} // '') eq 'MSWin32'
            || $^O =~ /^(MSWin32|VMS)$/);
REPAIRED
        $new_skip =~ s/\R+\z//;
        die "unexpected verify skip anchor\n"
            unless $$text =~ s/\Q$old_skip\E/$new_skip/;
    }
);
