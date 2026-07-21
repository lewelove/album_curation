#!/usr/bin/env fish

if test (count $argv) -lt 1
    echo "Usage: (basename (status filename)) <URL>"
    exit 1
end

set url $argv[1]
set dest_dir "Digital Covers"

mkdir -p $dest_dir

set clean_url (string replace -r '\?.*' '' $url)
set filename (basename $clean_url)
set ext (string match -r '\.[^.]+$' $filename)

set now_in_unix (date +%s)
set output_file "$dest_dir/source$now_in_unix$ext"

wget -O $output_file $url
