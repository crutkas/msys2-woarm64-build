#!/usr/bin/perl
use strict;
use warnings;
use Digest::SHA qw(sha256_hex);

my $path = "crypto/threads_win.c";
open(my $input, "<:raw", $path) or die "cannot read $path: $!";
local $/;
my $text = <$input>;
close($input) or die "cannot close $path: $!";

my $original_hash =
    "0f21e5027f84594ba7dd38942d374376b35d98ec765eee572110413d1c513940";
my $repaired_hash =
    "23ad2f6fef6467ebfc8a85ae3e3458e565bdd74a36aa78c8c6a5156ee7afd823";
my $current_hash = sha256_hex($text);
exit 0 if $current_hash eq $repaired_hash;
die "unexpected OpenSSL Windows thread source ($current_hash)\n"
    unless $current_hash eq $original_hash;

my $old = <<'ORIGINAL';
void *ossl_rcu_uptr_deref(void **p)
{
    return (void *)*p;
}

void ossl_rcu_assign_uptr(void **p, void **v)
{
    InterlockedExchangePointer((void *volatile *)p, (void *)*v);
}
ORIGINAL
chomp($old);
my $new = <<'REPAIRED';
void *ossl_rcu_uptr_deref(void **p)
{
#if defined(__GNUC__)
    return __atomic_load_n(p, __ATOMIC_ACQUIRE);
#else
    return InterlockedCompareExchangePointer((void *volatile *)p, NULL, NULL);
#endif
}

void ossl_rcu_assign_uptr(void **p, void **v)
{
#if defined(__GNUC__)
    __atomic_store_n(p, *v, __ATOMIC_RELEASE);
#else
    InterlockedExchangePointer((void *volatile *)p, (void *)*v);
#endif
}
REPAIRED
chomp($new);
die "unexpected OpenSSL Windows RCU anchor\n"
    unless $text =~ s/\Q$old\E/$new/;

my $actual_repaired_hash = sha256_hex($text);
die "unexpected repaired OpenSSL Windows thread source ($actual_repaired_hash)\n"
    unless $actual_repaired_hash eq $repaired_hash;

open(my $output, ">:raw", $path) or die "cannot write $path: $!";
print {$output} $text or die "cannot update $path: $!";
close($output) or die "cannot close updated $path: $!";
