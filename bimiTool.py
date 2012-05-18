#!/usr/bin/python
# vim: set fileencoding=utf-8
# ----------------------------------------------------------------------------#
#    Copyright 2012 Julian Weitz                                              #
#                                                                             #
#    This program is free software: you can redistribute it and/or modify     #
#    it under the terms of the GNU General Public License as published by     #
#    the Free Software Foundation, either version 3 of the License, or        #
#    any later version.                                                       #
#                                                                             #
#    This program is distributed in the hope that it will be useful,          #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of           #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            #
#    GNU General Public License for more details.                             #
#                                                                             #
#    You should have received a copy of the GNU General Public License        #
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.    #
# ----------------------------------------------------------------------------#
import sys, datetime, logging
from bimibase import BimiBase
from bimiconfig import BimiConfig

try:
    from gi.repository import Gtk, Pango
except ImportError:
    print("--------------------------------------------------------------------------")
    print("| Check your python GTK+3 setup! (Debian/Ubuntu: install gir1.2-gtk-3.0) |")
    print("--------------------------------------------------------------------------")
    sys.exit(1)


class BiMiTool:
    def __init__(self):
        self._logger = logging.getLogger('BiMiTool')

        # Create DataBase-object
        self.db = BimiBase( BimiConfig.option('db_path') )

        # Load main window from GtkBuilder file
        self.gui = Gtk.Builder()
        widgets = ['main_window', 'image1', 'image2', 'image3', 'image1',
                   'drinks_menu', 'accounts_menu', 'transactions_menu',
                   'adjustment7', 'adjustment8', 'adjustment9', 'adjustment10']
        self.gui.add_objects_from_file( BimiConfig.option('gui_path'), widgets )
        try:
            # Create our dictionay and connect it
            dic = {'consume_clicked': self.consumeDrinks,
                   'add_account': self.popAddAccWindow,
                   'edit_account': self.popEditAccWindow,
                   'acc_view_button_pressed': self.accountsViewClicked,

                   'delete_account': self.deleteAccount,
                   'acc_view_row_act': self.updateTransactionsView,
                   'drinks_view_button_pressed': self.drinksViewClicked,
                   'delete_drink': self.deleteDrink,

                   'transactions_view_button_pressed': self.transactionsViewClicked,
                   'undo_transaction': self.undoTransaction,

                   'add_drink': self.popAddDrinkWindow,
                   'edit_drink': self.popEditDrinkWindow,

                   'generate_mail': self.generateMail,
                   #"preferences_activate": self.prefsPopup,
                   'main_window_destroyed': Gtk.main_quit,
                   'quit_activate' : Gtk.main_quit}
            self.gui.connect_signals(dic)
        except:
            self._logger.critical('Autoconnection of widgets failed! Check if %s exists.', BimiConfig.option('gui_path'))
            sys.exit(1)
        self.main_window = self.gui.get_object('main_window')
        self.main_window.show_all()
        self.accounts_context_menu = self.gui.get_object('accounts_menu')
        self.drinks_context_menu = self.gui.get_object('drinks_menu')
        self.transactions_context_menu = self.gui.get_object('transactions_menu')
        self.account_window = None  ##< The most recent popup window to add/edit accounts
        self.drink_window = None    ##< The most recent popup window to add/edit drinks
        self.mail_window = None     ##< The most recent popup window to get the mail text

        # Misc member variables
        self.edit_acc_infos = []    ##< Stores [account_id, name] while edit_account window is open
        self.edit_drink_infos = []  ##< Stores row from drinks_list while edit_drink window is open
        self.event_pos = []         ##< [x,y] pos from event object that activated the last context menu popup

        # Create column-headers and add accounts from database into rows
        self.accounts_list = Gtk.ListStore(int, str)
        self.accounts_view = self.gui.get_object("accounts_view")
        self.accounts_view.set_model(self.accounts_list)
        self.accounts_name_col = Gtk.TreeViewColumn('Account name', Gtk.CellRendererText(), text=1)
        self.accounts_view.append_column(self.accounts_name_col)
        self.updateAccountsView()

        # Create column headers for drinks_view
        ## \var self.drinks_list for each float a str for visualisation
        # (did, dname, sPrice, str sPrice, pPrice, str pPrice, deposit, str deposit, fBottles, eBottles, kings, str for comboboxes)
        self.drinks_list = Gtk.ListStore(int, str, float, str, float, str, float, str, int, int, bool, str)
        self.drinks_view = self.gui.get_object("drinks_view")
        self.drinks_view.set_model(self.drinks_list)
        col_names = ['Name', 'Sales Price', 'Purchase Price', 'Deposit', 'Full Bottles', 'Empty Bottles', 'Kings']
        render_cols = [1,3,5,7,8,9,10]
        for i in range(len(col_names)):
            renderer = Gtk.CellRendererText()
            renderer.set_alignment(1.0,0.5)
            drinks_view_col = Gtk.TreeViewColumn(col_names[i], renderer, text=render_cols[i])
            self.drinks_view.append_column(drinks_view_col)
        self.updateDrinksView()

        # Create column headers for transactions_view
        self.transactions = [] ##< Contains all informations and transactions from one account
        self.transactions_list = Gtk.ListStore(int, str, str)
        self.transactions_view = self.gui.get_object('transactions_view')
        self.transactions_view.set_model(self.transactions_list)
        col_names = ['Date', 'Value']
        for i in range(len(col_names)):
            renderer = Gtk.CellRendererText()
            renderer.set_alignment(1.0,0.5)
            trans_view_col = Gtk.TreeViewColumn(col_names[i], renderer, text=i+1)
            self.transactions_view.append_column(trans_view_col)

        # Set up and add text from database to comboboxes and spinbuttons
        self.drinks_comboxes_spinbuttons = [] ##< Contains tuples (combobox,spinbutton)
        for i in range(4):
            cbox = self.gui.get_object('drinks_select' + str(i))
            cbox.set_model(self.drinks_list)
            cell = Gtk.CellRendererText()
            cbox.pack_start(cell, True)
            cbox.add_attribute(cell, 'text', 11)
            self.drinks_comboxes_spinbuttons.append( (cbox, self.gui.get_object('drinks_amount' + str(i))) )
        self.updateDrinksComboBoxes()


    ## Called if mouse button is pressed in self.accounts_view
    #
    #  Checks for right mouse click and opens context menu
    def accountsViewClicked(self, widget, event):
        if (event.button == 3):
            self.event_pos = (event.x,event.y)
            if widget.get_path_at_pos(event.x,event.y) is None:
                self.gui.get_object('acc_menu_edit').set_sensitive(False)
                self.gui.get_object('acc_menu_delete').set_sensitive(False)
            else:
                self.gui.get_object('acc_menu_edit').set_sensitive(True)
                self.gui.get_object('acc_menu_delete').set_sensitive(True)
            self.accounts_context_menu.popup(None, None, None, None, event.button, event.time)
            return True


    def accountWindowCancel(self, widget):
        self.account_window.destroy()


    def accountWindowDestroyed(self, widget):
        self.account_window = None
        self.edit_acc_infos = []


    ## Commits data entered in account_window to the database
    def accountWindowSave(self, widget):
        self.account_window.hide()
        acc_name = self.gui.get_object('edit_acc_entry').get_text()
        credit = int(round(100*self.gui.get_object('edit_acc_spinbutton').get_value()))
        if self.edit_acc_infos:
            if acc_name != self.edit_acc_infos[1]:
                self.db.setAccountName(self.edit_acc_infos[0], acc_name)
            if credit != 0:
                self.db.addCredit(self.edit_acc_infos[0],credit)
        else:
            self.db.addAccount(acc_name, credit)
        self.updateAccountsView()
        self.account_window.destroy()


    ## Builds the account window and connects signals
    #
    #  Drops following after being called for the second time 0_o
    #  Gtk-CRITICAL **: gtk_spin_button_get_adjustment: assertion `GTK_IS_SPIN_BUTTON (spin_button)' failed
    def buildAccountWindow(self):
        self.gui.add_objects_from_file( BimiConfig.option('gui_path'), ['account_window', 'adjustment1'] )
        self.account_window = self.gui.get_object('account_window')
        self.gui.connect_signals({'account_window_cancel': self.accountWindowCancel,
                                  'account_window_save': self.accountWindowSave,
                                  'account_window_destroyed': self.accountWindowDestroyed})


    ## Builds the drink window and connects signals
    #
    #  No problems with gtk_spin_button_get_adjustment here, stupid gtk >_<
    def buildDrinkWindow(self):
        widgets = ['drink_window', 'adjustment2', 'adjustment3', 'adjustment4', 'adjustment5', 'adjustment6']
        self.gui.add_objects_from_file( BimiConfig.option('gui_path'), widgets )
        self.drink_window = self.gui.get_object('drink_window')
        self.gui.connect_signals({'drink_window_cancel': self.drinkWindowCancel,
                                  'drink_window_save': self.drinkWindowSave,
                                  'drink_window_destroyed': self.drinkWindowDestroyed})


    def buildMailWindow(self):
        self.gui.add_objects_from_file( BimiConfig.option('gui_path'), ['mail_window', 'mail_buffer'] )
        self.mail_window = self.gui.get_object('mail_window')
        self.gui.connect_signals({'mail_window_destroyed': self.mailWindowDestroyed})
        text_view =  self.gui.get_object('mail_view')
        text_view.modify_font( Pango.FontDescription('monospace normal 10') )


    def consumeDrinks(self, widget):
        lstore, it =  self.accounts_view.get_selection().get_selected()
        if it is None:
            self._logger.info("No account selected, can't add drinks :(")
            return

        dids_amounts = []
        row_num = -1
        amount = 0
        for cbox,sbutton in self.drinks_comboxes_spinbuttons:
            row_num = cbox.get_active()
            amount = sbutton.get_value_as_int()
            if row_num != -1 and amount > 0:
                dids_amounts.append( (self.drinks_list[(row_num,0)][0], amount) )

        self.db.consumeDrinks( lstore.get_value(it, 0), dids_amounts )

        # Reset Spinbuttons
        for item in self.drinks_comboxes_spinbuttons:
            item[1].set_value(0)

        self.updateTransactionsView(self.accounts_view)


    def deleteAccount(self, widget):
        row_num = self.accounts_view.get_path_at_pos(self.event_pos[0], self.event_pos[1])[0]
        self.db.delAccount( self.accounts_list[(row_num,0)][0] )
        self.updateAccountsView()


    def deleteDrink(self, widget):
        row_num = self.drinks_view.get_path_at_pos(self.event_pos[0], self.event_pos[1])[0]
        self.db.delDrink( self.drinks_list[(row_num,0)][0] )
        self.updateDrinksView()
        self.updateDrinksComboBoxes()


    def undoTransaction(self, widget):
        row_num = self.transactions_view.get_path_at_pos(self.event_pos[0], self.event_pos[1])[0]
        self.db.undoTransaction( self.transactions_list[(row_num,0)][0] )
        self.updateTransactionsView(self.accounts_view)


    def drinksViewClicked(self, widget, event):
        if (event.button == 3):
            self.event_pos = (event.x,event.y)
            if widget.get_path_at_pos(event.x,event.y) is None:
                self.gui.get_object('drinks_menu_edit').set_sensitive(False)
                self.gui.get_object('drinks_menu_delete').set_sensitive(False)
            else:
                self.gui.get_object('drinks_menu_edit').set_sensitive(True)
                self.gui.get_object('drinks_menu_delete').set_sensitive(True)
            self.drinks_context_menu.popup(None, None, None, None, event.button, event.time)


    def drinkWindowCancel(self, widget):
        self.drink_window.destroy()


    def drinkWindowDestroyed(self, widget):
        self.drink_window = None
        self.edit_drink_infos = []


    def drinkWindowSave(self, widget):
        self.drink_window.hide()
        values = []
        values.append( self.gui.get_object('edit_drink_entry').get_text() )
        for i in range(3):
            values.append(int(round(100*self.gui.get_object('edit_drink_spinbutton'+str(i)).get_value())))
        values.append( self.gui.get_object('edit_drink_spinbutton3').get_value() )
        values.append( self.gui.get_object('edit_drink_spinbutton4').get_value() )
        values.append(True)

        if self.edit_drink_infos:
            self.db.setDrink(self.edit_drink_infos[0], values)
        else:
            self.db.addDrink(values)
        self.drink_window.destroy()
        self.updateDrinksView()
        self.updateDrinksComboBoxes()


    ## Generates mail text from mail file and database
    #
    #  size_request of scrolledwindow and textview doesn't work properly,
    #  which results in a too small window. stupid gtk
    def generateMail(self, widget):
        # Open mail file for reading
        try:
            mail_file = open(BimiConfig.option('mail_path'), 'r')
        except IOError as io:
            self._logger.error('File %s required to generate mail not found! [io: %s]',\
                               BimiConfig.option('mail_path'), io)
            return

        if self.mail_window is None:
            self.buildMailWindow()
        else:
            #TODO: Raise window
            pass

        mail_buffer = self.gui.get_object('mail_buffer')
        mail_buffer.set_text('')
        for i,line in enumerate(mail_file):
            # substitute $kings in file with the kings information
            if line.find('$kings:') != -1:
                parts = list(line.partition('$kings:'))
                acc_drink_quaffed = self.db.kings()

                # Check if there are kings
                if acc_drink_quaffed:
                    len_acc = max(map(lambda x: len(x[0]), acc_drink_quaffed))
                    len_drink = max(map(lambda x: len(x[1]), acc_drink_quaffed))
                    len_quaffed = max(map(lambda x: len(str(x[2])), acc_drink_quaffed))
                    parts[2] = parts[2].replace('$name', '{name:<'+str(len_acc)+'}', 1)
                    parts[2] = parts[2].replace('$drink', '{drink:<'+str(len_drink)+'}', 1)
                    parts[2] = parts[2].replace('$amount', '{amount:>'+str(len_quaffed)+'}', 1)

                    for item in acc_drink_quaffed:
                        try:
                            insert = unicode(parts[0]) + unicode(parts[2]).format(name=item[0], drink=item[1], amount=item[2])
                        except StandardError as err:
                            self._logger.error("Line %s in file %s is not as expected! [err: %s]", str(i+1), BimiConfig.option('mail_path'), err)
                            return
                        mail_buffer.insert_at_cursor(insert)
                else:
                    mail_buffer.insert_at_cursor( '{}The Rabble is delighted, there are no Kings and Queens!'.format(parts[0])+'\n' )

            # substitute $accInfos in file with the account informations
            elif line.find('$accInfos:') != -1:
                cur_symbol = BimiConfig.option('currency')
                parts = list(line.partition('$accInfos:'))

                accnames_balances = []
                for aid, name in self.db.accounts():
                    balance = sum(map( lambda x: x[2]*x[3], self.db.transactions(aid) )) / 100.0 - BimiConfig.option('deposit')
                    accnames_balances.append( (name, balance) )

                # Check if there are accounts in DB
                if accnames_balances:
                    len_acc = max(map(lambda x: len(x[0]), accnames_balances))
                    len_balance = max(map(lambda x: len(str(int(x[1]))), accnames_balances)) + 3 # +3 because .00
                    parts[2] = parts[2].replace('$name', '{name:<'+str(len_acc)+'}', 1)
                    parts[2] = parts[2].replace('$balance', '{balance:>'+str(len_balance)+'.2f}'+cur_symbol, 1)

                    for item in accnames_balances:
                        try:
                            insert = parts[0] + parts[2].format(name=item[0], balance=item[1])
                        except StandardError as err:
                            self._logger.error("'$accInfos:' line in %s file is broken! [err: %s]", BimiConfig.option('mail_path'), err)
                            return
                        mail_buffer.insert_at_cursor(insert)
                else:
                    mail_buffer.insert_at_cursor( '{}No one lives in BimiTool-land ;_;'.format(parts[0])+'\n' )
            else:
                mail_buffer.insert_at_cursor(line)
        mail_file.close()
        self.mail_window.show_all()


    def mailWindowDestroyed(self, widget, stuff=None):
        self.mail_window = None


    ## Opens account_window
    def popAddAccWindow(self, widget):
        if self.account_window is None:
            self.buildAccountWindow()
        else:
            #TODO: Raise window
            pass
        self.account_window.set_title('Add account')
        self.gui.get_object('edit_acc_entry').set_text('Insert name')
        self.gui.get_object('edit_acc_entry').select_region(0,-1)
        self.gui.get_object('edit_acc_spinbutton').set_value(0.0)
        self.account_window.show()


    def popAddDrinkWindow(self, widget):
        if self.drink_window is None:
            self.buildDrinkWindow()
        else:
            #TODO: Raise window
            pass
        self.drink_window.set_title('Add drink')
        self.gui.get_object('edit_drink_entry').set_text('Insert name')
        self.gui.get_object('edit_drink_entry').select_region(0,-1)
        for i in range(5):
            self.gui.get_object('edit_drink_spinbutton'+str(i)).set_value(0)
        self.drink_window.show()


    ## Opens account_window and loads account infos
    def popEditAccWindow(self, widget):
        if self.account_window is None:
            self.buildAccountWindow()
        else:
            #TODO: Raise window
            pass
        self.account_window.set_title('Edit account')
        row_num = self.accounts_view.get_path_at_pos(self.event_pos[0], self.event_pos[1])[0]
        self.edit_acc_infos =  self.accounts_list[(row_num,)]
        self.gui.get_object('edit_acc_entry').set_text( self.edit_acc_infos[1] )
        self.gui.get_object('edit_acc_spinbutton').set_value(0.0)
        self.account_window.show()


    def popEditDrinkWindow(self, widget):
        if self.drink_window is None:
            self.buildDrinkWindow()
        else:
            #TODO: Raise window
            pass
        self.drink_window.set_title('Edit drink')
        row_num = self.drinks_view.get_path_at_pos(self.event_pos[0], self.event_pos[1])[0]
        self.edit_drink_infos = self.drinks_list[(row_num,)]
        self.gui.get_object('edit_drink_entry').set_text( self.edit_drink_infos[1] )
        cols = [2,4,6,8,9]
        for i in range(5):
            self.gui.get_object('edit_drink_spinbutton'+str(i)).set_value( self.edit_drink_infos[cols[i]] )
        self.drink_window.show()


    def transactionsViewClicked(self, widget, event):
        if (event.button == 3):
            self.event_pos = (event.x,event.y)
            if widget.get_path_at_pos(event.x,event.y) is not None:
                #diff = int(str(self.transactions_view.get_path_at_pos(event.x, event.y)[0]))
                #diff -= len(self.transactions_list)
                row_num = self.transactions_view.get_path_at_pos(event.x, event.y)[0]
                if self.transactions_list[(row_num,0)][0] != -1: # Check if a transaction was clicked
                    self.gui.get_object('transactions_menu_delete').set_sensitive(True)
                    self.transactions_context_menu.popup(None, None, None, None, event.button, event.time)


    ## Loads accounts infos from database and updates accounts_list
    def updateAccountsView(self):
        self.accounts_list.clear()
        db_account_list = self.db.accounts()
        for item in db_account_list:
            self.accounts_list.append(item)


    def updateDrinksComboBoxes(self):
        # set active items for comboxes
        for i in range(len(self.drinks_comboxes_spinbuttons)):
            if i < len(self.drinks_list):
                self.drinks_comboxes_spinbuttons[i][0].set_active(i)


    def updateDrinksView(self):
        self.drinks_list.clear()
        cur_symbol = BimiConfig.option('currency')
        for item in self.db.drinks():
            self.drinks_list.append( [item[0], item[1],\
                                      item[2]/100.0, str(item[2]/100.0) + cur_symbol,\
                                      item[3]/100.0, str(item[3]/100.0) + cur_symbol,\
                                      item[4]/100.0, str(item[4]/100.0) + cur_symbol,\
                                      item[5], item[6], item[7],\
                                      item[1] + ' @ ' + str(item[2]/100.0) + cur_symbol] )


    def updateTransactionsView(self, widget):
        self.transactions_list.clear()
        lstore, it =  self.accounts_view.get_selection().get_selected()
        if it is None:
            return
        self.transactions = self.db.transactions( lstore.get_value(it, 0) )

        if self.transactions:
            # show only one row per transaction
            cur_symbol = BimiConfig.option('currency')
            total = 0.0
            tid_date_value = [self.transactions[0][0], str(self.transactions[0][4].date()), 0.0]
            for i,item in enumerate(self.transactions):
                if tid_date_value[0] == item[0]:
                    tid_date_value[2] += item[3]/100.0*item[2]
                else:
                    tid_date_value[2] = str(tid_date_value[2]) + cur_symbol
                    self.transactions_list.append(tid_date_value)
                    tid_date_value[0] = item[0]
                    tid_date_value[1] = str(item[4].date())
                    tid_date_value[2] = item[3]/100.0*item[2]
                total += item[3]/100.0*item[2]
            tid_date_value[2] = str(tid_date_value[2]) + cur_symbol
            self.transactions_list.append(tid_date_value)
            self.transactions_list.append( [-1, 'Deposit', str(-BimiConfig.option('deposit')) + cur_symbol] )
            self.transactions_list.append( [-1, 'Balance', str(total - BimiConfig.option('deposit')) + cur_symbol] )


if __name__ == "__main__":
    # Initialize logger
    logging.basicConfig(level=logging.DEBUG,\
                        format='%(asctime)s [%(levelname)8s] Module %(name)s in line %(lineno)s %(funcName)s(): %(message)s',\
                        datefmt='%Y-%m-%d %H:%M:%S')
    BimiConfig.load()
    bmt = BiMiTool()
    Gtk.main()
