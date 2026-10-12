using Microsoft.EntityFrameworkCore;
using NotesApi.Models;

namespace NotesApi.Data;

public class NotesDbContext(DbContextOptions<NotesDbContext> options) : DbContext(options)
{
    public DbSet<Note> Notes => Set<Note>();
    public DbSet<NoteTag> NoteTags => Set<NoteTag>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Note>(e =>
        {
            e.Property(n => n.Title).HasMaxLength(120).IsRequired();
            e.Property(n => n.Body).HasMaxLength(2000);
            e.Property(n => n.OwnerId).HasMaxLength(64).IsRequired();
            e.HasIndex(n => new { n.OwnerId, n.UpdatedUtc });
            e.HasMany(n => n.Tags).WithOne().HasForeignKey(t => t.NoteId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<NoteTag>(e =>
        {
            e.Property(t => t.Name).HasMaxLength(24).IsRequired();
            e.HasIndex(t => new { t.NoteId, t.Name }).IsUnique();
        });
    }
}
