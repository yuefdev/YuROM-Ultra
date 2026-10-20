// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control.probe;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.provider.DocumentsProvider;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

/** Isolated storage for exercising the Settings activity-result import/export path. */
public final class TestDocuments extends DocumentsProvider {
    private File directory;
    public boolean onCreate(){directory=new File(getContext().getFilesDir(),"acceptance-documents");return directory.mkdirs()||directory.isDirectory();}
    private File file(String id)throws FileNotFoundException{
        if("root".equals(id))return directory;
        if(!id.matches("[A-Za-z0-9_.-]+"))throw new FileNotFoundException("Invalid fixture document");
        return new File(directory,id);
    }
    public Cursor queryRoots(String[] projection){
        MatrixCursor cursor=new MatrixCursor(projection==null?new String[]{"root_id","document_id","title","flags","mime_types","available_bytes"}:projection);
        cursor.newRow().add("root_id","artisan-test").add("document_id","root").add("title","Artisan test files")
                .add("flags",DocumentsContract.Root.FLAG_SUPPORTS_CREATE|DocumentsContract.Root.FLAG_LOCAL_ONLY).add("mime_types","*/*").add("available_bytes",directory.getFreeSpace());
        return cursor;
    }
    private void row(MatrixCursor cursor,File file,String id){
        cursor.newRow().add("document_id",id).add("_display_name","root".equals(id)?"Artisan test files":file.getName())
                .add("mime_type",file.isDirectory()?DocumentsContract.Document.MIME_TYPE_DIR:file.getName().endsWith(".zip")?"application/zip":"application/json")
                .add("flags",file.isDirectory()?DocumentsContract.Document.FLAG_DIR_SUPPORTS_CREATE:DocumentsContract.Document.FLAG_SUPPORTS_WRITE)
                .add("_size",file.length()).add("last_modified",file.lastModified());
    }
    private MatrixCursor cursor(String[] projection){return new MatrixCursor(projection==null?new String[]{"document_id","_display_name","mime_type","flags","_size","last_modified"}:projection);}
    public Cursor queryDocument(String id,String[] projection)throws FileNotFoundException{MatrixCursor cursor=cursor(projection);row(cursor,file(id),id);return cursor;}
    public Cursor queryChildDocuments(String id,String[] projection,String sort)throws FileNotFoundException{
        MatrixCursor cursor=cursor(projection);File[] files=file(id).listFiles();if(files!=null)for(File child:files)row(cursor,child,child.getName());return cursor;
    }
    public String createDocument(String parent,String mime,String name)throws FileNotFoundException{
        if(!"root".equals(parent))throw new FileNotFoundException("Invalid fixture root");File target=file(name);
        try{if(!target.createNewFile())throw new IOException("Fixture document exists");}catch(IOException e){throw new FileNotFoundException(e.toString());}return target.getName();
    }
    public ParcelFileDescriptor openDocument(String id,String mode,CancellationSignal cancel)throws FileNotFoundException{return ParcelFileDescriptor.open(file(id),ParcelFileDescriptor.parseMode(mode));}
}
