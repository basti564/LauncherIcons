find . -type f -name 'oculus_*' > .all_files.txt

split -l 200 .all_files.txt .chunk_

for file in .chunk_*; do
    echo "1"
    xargs -a "$file" git add

    git commit -m "update icons"

    git push
done

rm .all_files.txt .chunk_*

