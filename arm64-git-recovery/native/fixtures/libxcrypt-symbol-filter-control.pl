use strict;
use warnings;

@ARGV == 1 or die "usage: $0 PATCHED_SYMBOLS_STATIC_TEST\n";
open my $source, '<', $ARGV[0] or die "open source: $!\n";
local $/;
my $text = <$source>;
close $source or die "close source: $!\n";
my @patterns = $text =~ /sub \{ \$_\[0\] !~ \/([^\n]+)\/ \}/g;
@patterns == 1 or die "Expected the single actual private-symbol filter\n";
my $private = qr/$patterns[0]/;
my %public = (
    '_crypt_ascii64' => 0,
    '.refptr._crypt_ascii64' => 0,
    '__compiler_private' => 0,
    '_Zpublic_cpp' => 1,
    'crypt' => 1,
    'crypt_r' => 1,
    '.refptr.crypt' => 1,
    '.refptr.unexpected' => 1,
    'unexpected_global' => 1,
    '_z_public' => 1,
    '._crypt_not_refptr' => 1,
    '.refptr._crypt' => 1,
);
for my $name (sort keys %public) {
    my $actual = $name !~ $private ? 1 : 0;
    die "Incorrect visibility for $name\n" if $actual != $public{$name};
}
print "12 actual Perl symbol-filter controls passed\n";
