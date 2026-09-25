<?php
    /*
       Simple solarmax visualizer php program written by zagibu@gmx.ch in July 2010
       This program was originally licensed under WTFPL 2 http://sam.zoy.org/wtfpl/
       Improvements by Frank Lassowski flassowski@gmx.de in August 2010
       This program is now licensed under GPLv2 or later http://www.gnu.org/licenses/gpl2.html
    */
   $title="Solaranlage";
   $slogan1="Photovoltaik-Anlage 1: XX kWp SolarMax";
   $link0="solarertrag.php";
   $link1="solarertrag.php?wr=1";

   echo "<div id=\"header\">\n";
   echo "<h1><a href=\"" . $link0 . "\">" . $title . "</a></h1>\n";
   echo "<h5> ";
   echo "<a href=\"" . $link1 . "\">" . $slogan1 . "</a> ";
   echo "</h5>\n";
   echo "</div>\n";
?>
