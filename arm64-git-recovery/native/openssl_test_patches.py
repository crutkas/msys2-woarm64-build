"""Bounded MSYS-specific OpenSSL test adaptations; compiled inputs are not modified."""

from sources import ContractError


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ContractError("OpenSSL test adaptation source shape changed")
    return text.replace(before, after)


def adapt_test(name, text):
    if name == "test/recipes/80-test_cmp_http.t":
        text = replace_once(text, "use POSIX;\n", "use POSIX;\nuse JSON::PP qw(decode_json);\n")
        text = replace_once(text, "my $server_fh;  # Server file handle\n",
                            "my $server_fh;  # Server file handle\nmy %native_server_controls;\n")
        text = replace_once(text, '    my $pid = open($server_fh, "$cmd 2>$Mock_serverlog |");',
                            r'''    my $native_control;
    local $ENV{OPENSSL_NATIVE_SERVER_CONTROL} = $ENV{OPENSSL_NATIVE_SERVER_CONTROL};
    if (($ENV{OPENSSL_NATIVE_TEST_PROFILE} // "") eq "msys") {
        $native_control = result_dir() . "/native-server-control";
        mkdir $native_control or die "create private native server control: $!";
        $ENV{OPENSSL_NATIVE_SERVER_CONTROL} = $native_control;
    }
    my $pid = open($server_fh, "$cmd 2>$Mock_serverlog |");''')
        text = replace_once(text, '    print "$server_name server PID=$pid\\n";',
                            '    $native_server_controls{$pid} = $native_control if $native_control;\n'
                            '    print "$server_name server PID=$pid\\n";')
        text = replace_once(text, "        if ($pid0 != $pid) {\n",
                            "        $pid = $pid0 if $native_control; # Do not signal a PID from a foreign MSYS namespace.\n"
                            "        if (!$native_control && $pid0 != $pid) {\n")
        return replace_once(text, '    print "Killing $server_name server with PID=$pid\\n";',
                            r'''    if (my $control = delete $native_server_controls{$pid}) {
        open my $stop, ">", "$control/stop" or die "request native server stop: $!";
        print {$stop} "stop\n";
        close $stop or die "close native server stop: $!";
        my $done = "$control/done.json";
        for (1 .. 600) {
            last if -f $done;
            select undef, undef, undef, 0.05;
        }
        open my $result, "<", $done or die "native server did not finish owned cleanup";
        my $record = decode_json(do { local $/; <$result> });
        close $result;
        die "native server stop failed" if $record->{timed_out}
            || (!$record->{stop_requested} && $record->{raw_exit} != 0);
        close $server_fh; # Reap our own pipe child, never a server-reported foreign PID.
        print "$server_name native server stopped through its owned process handle\n";
        return;
    }
    print "Killing $server_name server with PID=$pid\n";''')
    if name in ("apps/CA.pl", "apps/CA.pl.in"):
        return replace_once(text, 'my $CATOP = "/usr/ssl";',
                            'my $CATOP = $ENV{"OPENSSL_CA_DIR"} // "/usr/ssl";')
    if name == "test/recipes/80-test_ca.t":
        text = replace_once(text, "qw/:DEFAULT cmdstr data_file srctop_file/",
                            "qw/:DEFAULT cmdstr data_file srctop_file result_file/")
        anchor = 'my $std_openssl_cnf = srctop_file("apps", $^O eq "VMS" ? "openssl-vms.cnf" : "openssl.cnf");\n'
        addition = r'''
if (($ENV{OPENSSL_NATIVE_TEST_PROFILE} // "") eq "msys") {
    $ENV{OPENSSL_CA_DIR} = "./demoCA";
    open my $config_in, "<", $std_openssl_cnf or die "open test CA config: $!";
    my $config_text = do { local $/; <$config_in> };
    close $config_in or die "close test CA config: $!";
    my $changed = $config_text =~ s{^dir(\s*=\s*)/usr/ssl(\s|$)}{"dir" . $1 . "./demoCA" . $2}egm;
    die "Expected exactly the package CA and TSA directory defaults" unless $changed == 2;
    $std_openssl_cnf = result_file("test-local-openssl.cnf");
    open my $config_out, ">", $std_openssl_cnf or die "create private test CA config: $!";
    print {$config_out} $config_text;
    close $config_out or die "close private test CA config: $!";
}
'''
        return replace_once(text, anchor, anchor + addition)
    if name == "test/recipes/01-test_symbol_presence.t":
        text = replace_once(text, "my %defpath;\n", r'''my %defpath;
my $native_pe_exports = config('target') eq 'Cygwin-aarch64';
die "Native MSYS export reader is required"
    if $native_pe_exports && (!$ENV{OPENSSL_NATIVE_PE_EXPORT_READER} || !$ENV{OPENSSL_NATIVE_TEST_PYTHON});
''')
        text = replace_once(text, '    my $shlib_cmd = "nm -DPg $shlibpath{$_} 2> /dev/null";',
                            r'''    my $shlib_cmd = $native_pe_exports
        ? "\"$ENV{OPENSSL_NATIVE_TEST_PYTHON}\" \"$ENV{OPENSSL_NATIVE_PE_EXPORT_READER}\" \"$shlibpath{$_}\""
        : "nm -DPg $shlibpath{$_} 2> /dev/null";''')
        return replace_once(text, "    push @arrays, \\@shlib_lines unless disabled('shared');",
                            "    push @arrays, \\@shlib_lines unless disabled('shared') || $native_pe_exports;")
    raise ContractError(f"Unknown bounded OpenSSL test adaptation: {name}")


TEST_FILES = ("apps/CA.pl", "apps/CA.pl.in", "test/recipes/80-test_ca.t",
              "test/recipes/01-test_symbol_presence.t", "test/recipes/80-test_cmp_http.t")
