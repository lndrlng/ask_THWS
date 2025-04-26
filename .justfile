build-scraper VERSION:
    docker build -t ghcr.io/dav354/scraper:latest . && \
    docker tag ghcr.io/dav354/scraper:latest ghcr.io/dav354/scraper:$VERSION && \
    docker push ghcr.io/dav354/scraper:latest && \
    docker push ghcr.io/dav354/scraper:$VERSION

fmt:
    pre-commit run --all-files

compress FILE:
    tar -cf "{{without_extension(FILE)}}.tar.xz" \
        -I "xz -9 --threads=0" \
        "{{FILE}}"
