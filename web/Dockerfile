FROM php:8-apache
RUN apt update; apt install -y libpng-dev libjpeg-dev libfreetype6-dev fonts-dejavu-core
RUN docker-php-ext-configure gd --with-freetype --with-jpeg
RUN docker-php-ext-install mysqli iconv gd
RUN mkdir /var/www/html/img; chown -R www-data:www-data /var/www/html/img
