#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2010-2011 Zuza Software Foundation
#
# This file is part of translate.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

import sys
import os

from translate.storage import factory

from flask import current_app

from flask.ext.script import Command, Option, prompt_bool

class InitDB(Command):
    """create database tables"""
    option_list = (
        Option('--source-language', '-s', dest='source_langs', action='append'),
    )

    def run(self, source_langs):
        current_app.tmdb.init_db(source_langs)

class DeployDB(Command):
    """Optimise the database for deployment."""

    def run(self):
        if prompt_bool("This will permanently alter the database. Continue?"):
            tmdb = current_app.tmdb
            cursor = tmdb.get_cursor()
            cursor.execute(tmdb.DEPLOY_QUERY % {'slang': 'en'})
            tmdb.connection.commit()


class TMDBStats(Command):
    """Print some (possibly) interesting figures about the TM DB."""

    def run(self):
        cursor = current_app.tmdb.get_cursor()
        db_name = current_app.config.get("DB_NAME")
        query = """SELECT
            pg_size_pretty(pg_database_size(%s)),
            pg_size_pretty(pg_total_relation_size('sources_en')),
            pg_size_pretty(pg_total_relation_size('targets_en')),
            pg_size_pretty(pg_relation_size('sources_en')),
            pg_size_pretty(pg_relation_size('targets_en'))
        ;"""
        data = (
            db_name,
        )
        cursor.execute(query, data)

        result = cursor.fetchone()
        print "Complete database (%s):\t" % db_name, result[0]
        print "Complete size of sources_en:\t", result[1]
        print "Complete size of targets_en:\t", result[2]
        print "sources_en (table only):\t", result[3]
        print "targets_en (table only):\t", result[4]

        # On postgres 8.3 the casts below are required. They are not needed for
        # postgres 8.4.
        query = """COPY (
            SELECT relname,
                   indexrelname,
                   pg_size_pretty(pg_relation_size(CAST(indexrelname as text)))
            FROM pg_stat_all_indexes
            WHERE schemaname = 'public'
            ORDER BY pg_relation_size(CAST(indexrelname as text)) DESC
        ) TO STDOUT
        ;"""
        print
        print "Index sizes:"
        cursor.copy_expert(query, sys.stdout)


class BuildTMDB(Command):
    """Populate Translation Memory database from bilinugual translation files"""

    option_list = (
        Option('--source-language', '-s', dest='slang'),
        Option('--target-language', '-t', dest='tlang'),
        Option('--input', '-i', dest='filename'),
    )

    def run(self, slang, tlang, filename):
        self.source_lang = slang
        self.target_lang = tlang

        if not os.path.exists(filename):
            print >> sys.stderr, "cannot process %s: does not exist" % filename
        elif os.path.isdir(filename):
            self.handledir(filename)
        else:
            self.handlefile(filename)
        current_app.tmdb.connection.commit()

    def handlefile(self, filename):
        print "Importing strings from:", filename
        try:
            store = factory.getobject(filename)
            source_lang = self.source_lang or store.getsourcelanguage()
            target_lang = self.target_lang or store.gettargetlanguage()

            if not source_lang or not target_lang:
                print >> sys.stderr, "Missing source or target language. Won't import", filename
                return
        except Exception, e:
            print >> sys.stderr, str(e)
            return
        # do something useful with the store and db
        try:
            current_app.tmdb.add_store(store, source_lang, target_lang, commit=False)
        except Exception, e:
            print e
            raise

    def handlefiles(self, dirname, filenames):
        for filename in filenames:
            pathname = os.path.join(dirname, filename)
            if os.path.isdir(pathname):
                self.handledir(pathname)
            else:
                self.handlefile(pathname)

    def handledir(self, dirname):
        path, name = os.path.split(dirname)
        if name in ["CVS", ".svn", "_darcs", ".git", ".hg", ".bzr"]:
            return
        entries = os.listdir(dirname)
        self.handlefiles(dirname, entries)
 
